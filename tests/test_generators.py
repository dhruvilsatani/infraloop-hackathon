"""Starter-file generator: only for real gaps, deterministic, never overwrites, facts only, honest about what it skipped."""
import io, os, sys, tempfile, unittest, zipfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
from nodes.gap_identifier import identify_gaps
import generators
from generators import generate_files, manifest, to_zip_bytes, write_to_dir
from generators.model import HEADER


def scan(kind="python", has_dockerfile=False, has_cicd=False, tests=False, entry="main.py", lock=False, env=("DATABASE_URL", "SECRET_KEY"),
         env_example=False, extra_services=None, path="."):
    lang = {"python": "Python", "node": "JavaScript", "go": "Go"}[kind]
    svc = {"path": path, "main_language": lang, "entrypoints": [entry] if entry else [], "has_tests": tests, "has_dockerfile": has_dockerfile}
    lst = [svc] + (extra_services or [])
    return {"repo_kind": "application", "languages": {lang: 10},
            "infra_signals": {"has_cicd": has_cicd, "has_tests": tests, "has_dockerfile": has_dockerfile, "has_terraform": False, "has_k8s": False,
                              "has_helm": False, "has_monitoring_manifests": False},
            "secrets_findings": [], "services": {"count": len(lst), "list": lst}, "entrypoints_total": len(lst),
            "dependencies": {"web_framework": ["fastapi"] if kind == "python" else ["express"] if kind == "node" else []},
            "dependency_pinning": {"lockfile_present": lock},
            "env_vars": list(env), "repo_hygiene": {"env_example": env_example}}


def paths(bundle):
    return [f.path for f in bundle.files]


def get(bundle, path):
    return next(f for f in bundle.files if f.path == path)


class OnlyForRealGaps(unittest.TestCase):
    def test_nothing_is_generated_for_things_the_repo_has(self):
        s = scan(has_dockerfile=True, has_cicd=True, env_example=True)
        b = generate_files(s, identify_gaps(s))
        self.assertNotIn("Dockerfile", paths(b))
        self.assertNotIn(".github/workflows/ci.yml", paths(b))
        self.assertNotIn(".env.example", paths(b))

    def test_missing_dockerfile_and_ci_are_generated(self):
        s = scan()
        b = generate_files(s, identify_gaps(s))
        for p in ("Dockerfile", ".dockerignore", ".github/workflows/ci.yml", ".github/dependabot.yml", ".env.example"):
            self.assertIn(p, paths(b))

    def test_every_file_names_the_gap_it_closes(self):
        s = scan()
        issues = {g["issue"] for g in identify_gaps(s)}
        for f in generate_files(s).files:
            if f.path != ".env.example":
                self.assertIn(f.gap, issues, f.path)


class Deterministic(unittest.TestCase):
    def test_same_scan_same_files(self):
        s = scan()
        a, b = generate_files(s), generate_files(s)
        self.assertEqual([(f.path, f.content) for f in a.files], [(f.path, f.content) for f in b.files])
        self.assertEqual(manifest(a), manifest(b))

    def test_zip_bytes_are_stable(self):
        s = scan()
        self.assertEqual(to_zip_bytes(generate_files(s)), to_zip_bytes(generate_files(s)))


class Dockerfiles(unittest.TestCase):
    def test_python_runs_as_non_root_on_a_port(self):
        d = get(generate_files(scan("python", entry="main.py")), "Dockerfile").content
        self.assertIn("USER ", d)
        self.assertNotIn("USER root", d)
        self.assertIn("EXPOSE 8000", d)
        self.assertIn("main:app", d)

    def test_node_runs_as_non_root(self):
        d = get(generate_files(scan("node", entry="server.js")), "Dockerfile").content
        self.assertIn("USER node", d)
        self.assertIn("server.js", d)

    def test_node_uses_npm_ci_only_with_a_lockfile(self):
        self.assertIn("npm install", get(generate_files(scan("node", entry="server.js", lock=False)), "Dockerfile").content)
        self.assertIn("npm ci", get(generate_files(scan("node", entry="server.js", lock=True)), "Dockerfile").content)

    def test_dockerfile_says_what_it_assumed(self):
        a = get(generate_files(scan()), "Dockerfile")
        self.assertTrue(a.assumptions)
        self.assertTrue(a.review)
        self.assertIn(HEADER, a.content)

    def test_dockerignore_keeps_secrets_out_of_the_image(self):
        i = get(generate_files(scan()), ".dockerignore").content
        self.assertIn(".env", i)
        self.assertIn(".git", i)

    def test_existing_dockerfile_still_gets_a_dockerignore_if_missing(self):
        s = scan(has_dockerfile=True)
        b = generate_files(s, identify_gaps(s))
        self.assertNotIn("Dockerfile", paths(b))
        if any(g["issue"] == "no_dockerignore" for g in identify_gaps(s)):
            self.assertIn(".dockerignore", paths(b))


class Workflows(unittest.TestCase):
    def test_ci_and_dependabot_are_valid_yaml(self):
        b = generate_files(scan())
        for p in (".github/workflows/ci.yml", ".github/dependabot.yml"):
            doc = yaml.safe_load(get(b, p).content)
            self.assertIsInstance(doc, dict)
        ci = yaml.safe_load(get(b, ".github/workflows/ci.yml").content)
        self.assertIn("jobs", ci)

    def test_ci_only_uses_first_party_actions(self):
        text = get(generate_files(scan()), ".github/workflows/ci.yml").content
        for line in text.splitlines():
            if "uses:" in line:
                self.assertRegex(line.strip(), r"uses: actions/(checkout|setup-python|setup-node|setup-go)@v\d")

    def test_ci_runs_tests_only_when_the_scan_found_tests(self):
        self.assertNotIn("pytest", get(generate_files(scan(tests=False)), ".github/workflows/ci.yml").content)
        self.assertIn("pytest", get(generate_files(scan(tests=True)), ".github/workflows/ci.yml").content)

    def test_ci_builds_the_image_only_if_a_dockerfile_exists_or_is_generated(self):
        self.assertIn("docker build", get(generate_files(scan()), ".github/workflows/ci.yml").content)
        s = scan("go", entry="")
        s["repo_kind"] = "library"
        self.assertNotIn("docker build", get(generate_files(s, identify_gaps(s)), ".github/workflows/ci.yml").content)

    def test_dependabot_uses_the_right_ecosystem(self):
        self.assertIn("pip", get(generate_files(scan("python")), ".github/dependabot.yml").content)
        self.assertIn("npm", get(generate_files(scan("node", entry="server.js")), ".github/dependabot.yml").content)


class EnvExample(unittest.TestCase):
    def test_names_only_never_values(self):
        s = scan(env=("DATABASE_URL", "SECRET_KEY"))
        s["env_values"] = {"SECRET_KEY": "hunter2"}      # even if a value were around, it must not appear
        text = get(generate_files(s), ".env.example").content
        self.assertIn("DATABASE_URL=", text)
        self.assertIn("SECRET_KEY=", text)
        self.assertNotIn("hunter2", text)
        for line in text.splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                self.assertTrue(line.endswith("="), line)

    def test_not_generated_when_one_exists_or_there_are_no_variables(self):
        self.assertNotIn(".env.example", paths(generate_files(scan(env_example=True))))
        self.assertNotIn(".env.example", paths(generate_files(scan(env=()))))


class Services(unittest.TestCase):
    def test_each_service_gets_its_own_files_in_its_own_folder(self):
        extra = [{"path": "web", "main_language": "JavaScript", "entrypoints": ["server.js"], "has_tests": False, "has_dockerfile": False}]
        s = scan(path="api", extra_services=extra)
        p = paths(generate_files(s))
        for want in ("api/Dockerfile", "web/Dockerfile", "api/.dockerignore", "web/.dockerignore"):
            self.assertIn(want, p)
        self.assertNotIn("Dockerfile", p)

    def test_unknown_language_is_skipped_with_a_reason(self):
        extra = [{"path": "svc", "main_language": "Rust", "entrypoints": [], "has_tests": False, "has_dockerfile": False}]
        b = generate_files(scan(extra_services=extra))
        self.assertTrue(any("Rust" in s.reason for s in b.skipped))
        self.assertNotIn("svc/Dockerfile", paths(b))

    def test_more_than_five_services_are_capped_and_said_so(self):
        extra = [{"path": f"s{i}", "main_language": "Python", "entrypoints": ["main.py"], "has_tests": False, "has_dockerfile": False} for i in range(6)]
        b = generate_files(scan(extra_services=extra))
        self.assertEqual(len([p for p in paths(b) if p.endswith("Dockerfile")]), 5)
        self.assertTrue(any("more than 5" in s.reason for s in b.skipped))


class SkippedGapsSayWhy(unittest.TestCase):
    def test_gaps_a_file_cannot_fix_are_listed_with_a_reason(self):
        s = scan()
        b = generate_files(s, identify_gaps(s))
        self.assertTrue(b.skipped)
        for sk in b.skipped:
            self.assertTrue(sk.reason.strip())
        self.assertIn("Not generated", manifest(b))

    def test_hardcoded_secrets_are_never_fixed_by_a_file(self):
        s = scan()
        s["secrets_findings"] = [{"file": "config.py", "line": 3, "pattern_type": "generic_api_key", "location_kind": "source"}]
        b = generate_files(s, identify_gaps(s))
        self.assertTrue(any(sk.gap == "possible_hardcoded_secrets" for sk in b.skipped))


class WhenSomethingAlreadyExists(unittest.TestCase):
    """A repo that is part-way there: the generator fills the holes and leaves everything that exists alone."""

    def mixed(self):
        a = {"path": "api", "main_language": "Python", "entrypoints": ["main.py"], "has_tests": True, "has_dockerfile": True}
        b = {"path": "web", "main_language": "JavaScript", "entrypoints": ["server.js"], "has_tests": True, "has_dockerfile": False}
        s = scan(has_dockerfile=True, has_cicd=True, env_example=True, tests=True, lock=True, path="api")
        s["services"] = {"count": 2, "list": [a, b]}
        return s

    def test_service_without_a_dockerfile_gets_one_and_the_other_is_untouched(self):
        s = self.mixed()
        gaps = identify_gaps(s)
        self.assertIn("services_without_dockerfile", {g["issue"] for g in gaps})
        p = paths(generate_files(s, gaps))
        self.assertIn("web/Dockerfile", p)
        self.assertNotIn("api/Dockerfile", p)
        self.assertNotIn("Dockerfile", p)

    def test_every_generated_file_names_a_gap_that_really_exists(self):
        s = self.mixed()
        gaps = identify_gaps(s)
        issues = {g["issue"] for g in gaps}
        for f in generate_files(s, gaps).files:
            if f.path != ".env.example":
                self.assertIn(f.gap, issues, f.path)

    def test_existing_ci_is_never_replaced(self):
        s = self.mixed()
        self.assertNotIn(".github/workflows/ci.yml", paths(generate_files(s, identify_gaps(s))))

    def test_existing_env_example_is_never_replaced(self):
        s = self.mixed()
        self.assertNotIn(".env.example", paths(generate_files(s, identify_gaps(s))))

    def test_nothing_to_generate_says_so_instead_of_inventing_files(self):
        s = scan(has_dockerfile=True, has_cicd=True, env_example=True, tests=True, lock=True)
        gaps = [g for g in identify_gaps(s) if g["issue"] in ("no_iac", "no_tests")]
        b = generate_files(s, gaps)
        self.assertEqual(b.files, [])
        self.assertIn("No new files were generated", manifest(b))

    def test_no_gap_disappears_silently(self):
        """Every gap is either closed by a file or listed under 'Not generated' with a reason."""
        for s in (scan(), scan("node", entry="server.js"), self.mixed(), scan(has_dockerfile=True, has_cicd=True)):
            gaps = identify_gaps(s)
            b = generate_files(s, gaps)
            covered = {f.gap for f in b.files} | {k.gap for k in b.skipped} | {a.gap for a in b.advice}
            for g in gaps:
                self.assertIn(g["issue"], covered, g["issue"])


class FixesForExistingFiles(unittest.TestCase):
    """Gaps about files the repo already has: advice in the manifest, never an edit."""

    def scan(self):
        s = scan(has_dockerfile=True, has_cicd=True, env_example=True, tests=True, lock=True)
        s["repo_hygiene"].update({"dockerignore": True, "dependency_update_bot": True})
        s["dockerfile_quality"] = {"analysed": 1, "runs_as_root": "all", "runs_as_root_examples": ["Dockerfile"],
                                   "unpinned_base_image": "all", "unpinned_base_examples": ["Dockerfile"]}
        s["ci_quality"] = {"files_count": 1, "runs_tests": False, "security_scanning": False, "builds_container_image": False}
        s["sensitive_files"] = {"env_files": [".env"]}
        return s

    def test_problems_in_existing_files_become_advice_not_files(self):
        s = self.scan()
        b = generate_files(s, identify_gaps(s))
        self.assertEqual(b.files, [])
        got = {a.gap for a in b.advice}
        for want in ("containers_run_as_root", "unpinned_base_images", "ci_does_not_run_tests", "ci_does_not_build_images", "env_file_in_repo"):
            self.assertIn(want, got)

    def test_advice_quotes_what_the_scan_found(self):
        s = self.scan()
        a = next(x for x in generate_files(s, identify_gaps(s)).advice if x.gap == "env_file_in_repo")
        self.assertIn(".env", a.found)

    def test_manifest_has_the_section_and_says_nothing_was_applied(self):
        s = self.scan()
        m = manifest(generate_files(s, identify_gaps(s)))
        self.assertIn("## Fixes for files you already have", m)
        self.assertIn("never edits existing files", m)
        self.assertIn("USER app", m)
        self.assertIn("git rm --cached", m)

    def test_advice_comes_in_report_order_and_every_step_is_numbered(self):
        s = self.scan()
        gaps = identify_gaps(s)
        b = generate_files(s, gaps)
        order = [g["issue"] for g in gaps]
        idx = [order.index(a.gap) for a in b.advice]
        self.assertEqual(idx, sorted(idx))
        self.assertIn("\n1. ", manifest(b))

    def test_nothing_in_the_scanned_repo_is_modified_by_generating(self):
        import hashlib
        with tempfile.TemporaryDirectory() as d:
            for name, text in (("Dockerfile", "FROM python\n"), ("main.py", "x = 1\n")):
                with open(os.path.join(d, name), "w") as fh:
                    fh.write(text)
            before = {n: hashlib.sha256(open(os.path.join(d, n), "rb").read()).hexdigest() for n in os.listdir(d)}
            from scanner.scan import scan_repo
            sc = scan_repo(d)
            generate_files(sc, identify_gaps(sc))
            after = {n: hashlib.sha256(open(os.path.join(d, n), "rb").read()).hexdigest() for n in os.listdir(d)}
            self.assertEqual(before, after)


class Output(unittest.TestCase):
    def test_zip_has_manifest_and_every_file_under_one_folder(self):
        b = generate_files(scan())
        z = zipfile.ZipFile(io.BytesIO(to_zip_bytes(b)))
        names = z.namelist()
        self.assertIn("infraloop-generated/MANIFEST.md", names)
        for f in b.files:
            self.assertIn("infraloop-generated/" + f.path, names)
        self.assertTrue(all(n.startswith("infraloop-generated/") for n in names))

    def test_write_to_dir_writes_everything(self):
        b = generate_files(scan())
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "new")
            write_to_dir(b, out)
            self.assertTrue(os.path.isfile(os.path.join(out, "MANIFEST.md")))
            for f in b.files:
                with open(os.path.join(out, f.path), encoding="utf-8") as fh:
                    self.assertEqual(fh.read(), f.content)

    def test_write_to_dir_refuses_a_folder_that_has_files(self):
        b = generate_files(scan())
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "Dockerfile"), "w") as fh:
                fh.write("mine")
            with self.assertRaises(FileExistsError):
                write_to_dir(b, d)
            with open(os.path.join(d, "Dockerfile")) as fh:
                self.assertEqual(fh.read(), "mine")

    def test_write_to_dir_allows_an_empty_existing_folder(self):
        with tempfile.TemporaryDirectory() as d:
            write_to_dir(generate_files(scan()), d)
            self.assertTrue(os.path.isfile(os.path.join(d, "Dockerfile")))

    def test_manifest_lists_assumptions_and_review_items(self):
        m = manifest(generate_files(scan()))
        self.assertIn("Dockerfile", m)
        self.assertIn("not by an AI model", m)
        self.assertIn("Assumed:", m)
        self.assertIn("Check before you use it:", m)
        self.assertNotIn("a helper file, not a gap", m)


class Cli(unittest.TestCase):
    def test_generate_command_writes_a_new_folder_and_never_overwrites(self):
        import subprocess
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with tempfile.TemporaryDirectory() as d:
            app = os.path.join(d, "app")
            os.makedirs(app)
            with open(os.path.join(app, "main.py"), "w") as fh:
                fh.write("from fastapi import FastAPI\napp = FastAPI()\n")
            with open(os.path.join(app, "requirements.txt"), "w") as fh:
                fh.write("fastapi\nuvicorn\n")
            out = os.path.join(d, "out")
            r = subprocess.run([sys.executable, os.path.join(root, "infraloop.py"), "generate", app, "--out", out], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(os.path.isfile(os.path.join(out, "Dockerfile")))
            self.assertTrue(os.path.isfile(os.path.join(out, "MANIFEST.md")))
            self.assertEqual(os.listdir(app).count("Dockerfile"), 0)        # the scanned repo is never touched
            r2 = subprocess.run([sys.executable, os.path.join(root, "infraloop.py"), "generate", app, "--out", out], capture_output=True, text=True)
            self.assertEqual(r2.returncode, 1)
            self.assertIn("never overwrites", r2.stderr)


if __name__ == "__main__":
    unittest.main()
