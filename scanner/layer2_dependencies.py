import os
import json
import re

from scanner.common import walk_repo, is_test_path
from scanner.rules.dependency_map import DEPENDENCY_MAP
from scanner.rules.gpu_signals import detect_gpu_signals


def _parse_package_json(repo_path):
    """Walks the whole tree (not just the root) so dependencies declared in a
    monorepo's nested package.json files (e.g. mcp-servers/view-image-mcp/package.json)
    are actually seen, not just the manifest's existence (detect_monorepo finds the
    location separately -- this is what reads what's inside it)."""
    deps = {}
    for root, dirs, files in walk_repo(repo_path):
        if "package.json" not in files:
            continue
        path = os.path.join(root, "package.json")
        try:
            with open(path, "r", errors="ignore") as f:
                data = json.load(f)
        except (IOError, json.JSONDecodeError):
            continue
        deps.update(data.get("dependencies", {}))
        deps.update(data.get("devDependencies", {}))
        deps.update(data.get("optionalDependencies", {}))
    return list(deps.keys())


REQUIREMENTS_FILE_PATTERN = re.compile(r".*requirements?.*\.txt$", re.IGNORECASE)


def _parse_requirements_txt(repo_path):
    """Walks the whole tree and matches any filename containing "requirement"
    (singular or plural) ending in .txt -- not just the exact name "requirements.txt".
    Real repos commonly split this into requirements-dev.txt, requirement-prod.txt,
    dev-requirements.txt, etc. -- the old exact-match version silently returned zero
    dependencies for any of those, which is worse than just missing a few packages:
    it meant the whole dependency layer (and anything derived from it -- framework
    detection, third-party services, GPU signals) went dark for the entire project."""
    names = []
    for root, dirs, files in walk_repo(repo_path):
        for f in files:
            if not REQUIREMENTS_FILE_PATTERN.match(f):
                continue
            path = os.path.join(root, f)
            try:
                with open(path, "r", errors="ignore") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        # strip version specifiers like "==1.2.3", ">=1.0", etc.
                        name = re.split(r"[=<>~!\[]", line)[0].strip()
                        if name:
                            names.append(name)
            except (IOError, OSError):
                continue
    return names


def _each_file(repo_path, matcher):
    for root, dirs, files in walk_repo(repo_path):
        for f in files:
            if matcher(f):
                path = os.path.join(root, f)
                try:
                    if os.path.getsize(path) > 2_000_000:
                        continue
                    with open(path, "r", errors="ignore") as fh:
                        yield f, fh.read()
                except (IOError, OSError):
                    continue


def _strip_spec(item):
    item = item.strip().strip(",").strip('"').strip("'")
    return re.split(r"[=<>~!\[; @(]", item)[0].strip()


def _toml_arrays(body, only=None):
    """Quote-aware: the first ] OUTSIDE quotes closes the array (so "fastapi[standard]" doesn't)."""
    out = []
    for m in re.finditer(r"(?m)^\s*([\w\-\.]+)\s*=\s*\[", body):
        if only and m.group(1) not in only:
            continue
        i, quote, start = m.end(), None, m.end()
        while i < len(body):
            ch = body[i]
            if quote:
                if ch == quote:
                    quote = None
            elif ch in "\"'":
                quote = ch
            elif ch == "]":
                break
            i += 1
        out.append(body[start:i])
    return out


def _parse_pyproject_toml(repo_path):
    """Handles PEP 621 (dependencies = ["fastapi", ...] and optional-dependencies),
    PEP 735 dependency-groups and poetry-style name = "ver" tables -- every pyproject.toml in the tree."""
    names = []
    for _, text in _each_file(repo_path, lambda f: f == "pyproject.toml"):
        sections = re.split(r"(?m)^\[([^\]]+)\]\s*$", text)
        for i in range(1, len(sections) - 1, 2):
            header, body = sections[i].lower(), sections[i + 1]
            if header == "project":
                arrays = _toml_arrays(body, only={"dependencies"})
            elif "optional-dependencies" in header or "dependency-groups" in header:
                arrays = _toml_arrays(body)
            else:
                continue
            for arr in arrays:
                for item in re.findall(r"[\"']([^\"']+)[\"']", arr):
                    n = _strip_spec(item)
                    if n and re.match(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$", n):
                        names.append(n)
        in_deps = False
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("["):
                in_deps = "dependencies" in line.lower() or "dev-dependencies" in line.lower()
                continue
            if in_deps and "=" in line and not line.startswith(("#", '"')):
                n = line.split("=")[0].strip().strip('"').strip("'")
                if n and n.lower() != "python" and re.match(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$", n):
                    names.append(n)
    return names


IMPORT_ALIASES = {"sklearn": "scikit-learn", "cv2": "opencv-python", "PIL": "pillow", "yaml": "pyyaml",
                  "jwt": "pyjwt", "psycopg2": "psycopg2", "bs4": "beautifulsoup4", "tensorflow": "tensorflow",
                  "lightning": "pytorch-lightning", "pytorch_lightning": "pytorch-lightning"}
IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)


def _parse_python_imports(repo_path, limit=4000):
    """Projects without a requirements file (research code, scripts) still import their libraries.
    Only module NAMES that match a known package are kept."""
    found, seen = set(), 0
    for root, dirs, files in walk_repo(repo_path):
        for f in files:
            if not f.endswith(".py"):
                continue
            rel = os.path.relpath(os.path.join(root, f), repo_path)
            if is_test_path(rel):
                continue
            seen += 1
            if seen > limit:
                return sorted(found)
            try:
                if os.path.getsize(os.path.join(root, f)) > 300_000:
                    continue
                with open(os.path.join(root, f), "r", errors="ignore") as fh:
                    text = fh.read()
            except (IOError, OSError):
                continue
            for mod in set(IMPORT_RE.findall(text)):
                name = IMPORT_ALIASES.get(mod, mod).lower().replace("_", "-")
                if name in DEPENDENCY_MAP or mod.lower() in DEPENDENCY_MAP:
                    found.add(IMPORT_ALIASES.get(mod, mod).lower())
    return sorted(found)


def _parse_more_ecosystems(repo_path):
    """Pipfile, conda environment.yml, setup.py/setup.cfg, Elixir mix.exs, Dart pubspec.yaml, Scala build.sbt,
    Swift Package.swift -- names only."""
    names = []
    for f, text in _each_file(repo_path, lambda f: f in ("Pipfile", "environment.yml", "environment.yaml", "setup.py",
                                                         "setup.cfg", "mix.exs", "pubspec.yaml", "build.sbt",
                                                         "Package.swift")):
        if f == "Pipfile":
            in_pk = False
            for line in text.splitlines():
                if line.startswith("["):
                    in_pk = line.strip() in ("[packages]", "[dev-packages]")
                elif in_pk and "=" in line:
                    names.append(line.split("=")[0].strip().strip('"'))
        elif f.startswith("environment."):
            for m in re.finditer(r"^\s*-\s*([A-Za-z0-9_.\-]+)\s*(?:[=<>!~].*)?$", text, re.M):
                names.append(m.group(1))
        elif f in ("setup.py", "setup.cfg"):
            for block in re.findall(r"install_requires\s*[=:]\s*\[(.*?)\]", text, re.S):
                names += [_strip_spec(x) for x in re.findall(r"[\"']([^\"']+)[\"']", block)]
            m = re.search(r"(?m)^install_requires\s*=\s*\n((?:\s+.+\n?)+)", text)
            if m:
                names += [_strip_spec(l) for l in m.group(1).splitlines() if l.strip()]
        elif f == "mix.exs":
            names += re.findall(r"\{:([a-z_0-9]+),", text)
        elif f == "pubspec.yaml":
            in_dep = False
            for line in text.splitlines():
                if re.match(r"^(dependencies|dev_dependencies):", line):
                    in_dep = True
                elif re.match(r"^\S", line):
                    in_dep = False
                elif in_dep:
                    m = re.match(r"^  ([a-z_0-9]+):", line)
                    if m:
                        names.append(m.group(1))
        elif f == "build.sbt":
            names += [m[1] for m in re.findall(r'"([\w.\-]+)"\s*%%?\s*"([\w.\-]+)"', text)]
        elif f == "Package.swift":
            names += re.findall(r'\.package\(url:\s*"[^"]*/([\w.\-]+?)(?:\.git)?"', text)
    return [n for n in names if n]


def _parse_pom(repo_path):
    names = []
    for _, text in _each_file(repo_path, lambda f: f == "pom.xml"):
        names += re.findall(r"<artifactId>\s*([^<\s]+)\s*</artifactId>", text)
    return names


def _parse_gradle(repo_path):
    names = []
    for _, text in _each_file(repo_path, lambda f: f in ("build.gradle", "build.gradle.kts")):
        for m in re.finditer(r"""['"]([\w.\-]+):([\w.\-]+)(?::[^'"]*)?['"]""", text):
            names.append(m.group(2))
        names += re.findall(r"""id\s*\(?\s*['"]([\w.\-]+)['"]""", text)
    return names


def _parse_go_mod(repo_path):
    names = []
    for _, text in _each_file(repo_path, lambda f: f == "go.mod"):
        for m in re.finditer(r"^\s*(?:require\s+)?([\w.\-]+\.[\w.\-]+/[\w.\-/]+)\s+v[\w.\-+]+", text, re.M):
            path = m.group(1)
            names.append(path)
            parts = path.split("/")
            names.append("/".join(parts[-2:]))
            names.append(parts[-1])
    return names


def _parse_csproj(repo_path):
    names = []
    for _, text in _each_file(repo_path, lambda f: f.endswith(".csproj")):
        names += re.findall(r'PackageReference\s+Include="([^"]+)"', text)
        if 'Sdk="Microsoft.NET.Sdk.Web"' in text:
            names.append("microsoft.aspnetcore")
    return names


def _parse_gemfile(repo_path):
    names = []
    for _, text in _each_file(repo_path, lambda f: f == "Gemfile"):
        names += re.findall(r"^\s*gem\s+['\"]([^'\"]+)['\"]", text, re.M)
    return names


def _parse_composer(repo_path):
    names = []
    for _, text in _each_file(repo_path, lambda f: f == "composer.json"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        names += list((data.get("require") or {}).keys()) + list((data.get("require-dev") or {}).keys())
    return [n for n in names if n != "php"]


def _parse_cargo(repo_path):
    names = []
    for _, text in _each_file(repo_path, lambda f: f == "Cargo.toml"):
        in_deps = False
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("["):
                in_deps = "dependencies" in line
                m = re.match(r"\[(?:dev-|build-)?dependencies\.([\w\-]+)\]", line)
                if m:
                    names.append(m.group(1))
                continue
            if in_deps and "=" in line and not line.startswith("#"):
                names.append(line.split("=")[0].strip())
    return names


def detect_dependencies(repo_path):
    """Parses whichever manifest files exist, classifies every dependency it
    recognizes using the lookup table, and flags GPU likelihood from the same list."""
    all_names = []
    all_names += _parse_package_json(repo_path)
    all_names += _parse_requirements_txt(repo_path)
    all_names += _parse_pyproject_toml(repo_path)
    all_names += _parse_python_imports(repo_path)
    all_names += _parse_more_ecosystems(repo_path)
    for parser in (_parse_pom, _parse_gradle, _parse_go_mod, _parse_csproj, _parse_gemfile,
                   _parse_composer, _parse_cargo):
        all_names += parser(repo_path)

    lowercase_names = sorted({name.lower() for name in all_names if name})

    categorized = {}
    for name in lowercase_names:
        category = DEPENDENCY_MAP.get(name)
        if category:
            categorized.setdefault(category, []).append(name)

    gpu_signals = detect_gpu_signals(lowercase_names)

    return {
        "all_dependencies_found": lowercase_names,
        "categorized": categorized,
        "gpu_signals": gpu_signals,
    }


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    print(detect_dependencies(path))
