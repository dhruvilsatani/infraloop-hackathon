import os
import re

from scanner.common import walk_repo, GitIgnore
from scanner.rules.secret_patterns import scan_text_for_secrets

THIRD_PARTY_PACKAGES = {
    "stripe": "Stripe",
    "braintree": "Braintree",
    "sendgrid": "SendGrid",
    "nodemailer": "Nodemailer (email)",
    "twilio": "Twilio",
    "openai": "OpenAI",
    "spring-ai-starter-model-openai": "OpenAI", "spring-ai-openai-spring-boot-starter": "OpenAI",
    "spring-ai-starter-model-azure-openai": "Azure OpenAI", "spring-ai-azure-openai-spring-boot-starter": "Azure OpenAI",
    "spring-ai-starter-model-anthropic": "Anthropic", "spring-ai-anthropic-spring-boot-starter": "Anthropic",
    "spring-ai-starter-model-vertex-ai-gemini": "Google Gemini", "langchain4j-open-ai": "OpenAI",
    "anthropic": "Anthropic",
    "@anthropic-ai/sdk": "Anthropic",
    "@sendgrid/mail": "SendGrid",
    "@aws-sdk/client-ses": "Amazon SES (email)",
    "@google/generative-ai": "Google Gemini",
    "langchain": "LangChain (LLM framework)",
    "@supabase/supabase-js": "Supabase (hosted Postgres + auth)",
    "@supabase/ssr": "Supabase (hosted Postgres + auth)",
    "firebase": "Firebase", "firebase-admin": "Firebase",
    "@clerk/nextjs": "Clerk (auth)", "auth0": "Auth0", "@auth0/nextjs-auth0": "Auth0",
    "@planetscale/database": "PlanetScale (hosted MySQL)", "@neondatabase/serverless": "Neon (hosted Postgres)",
    "@vercel/postgres": "Vercel Postgres", "@upstash/redis": "Upstash Redis",
    "@sentry/nextjs": "Sentry", "@sentry/node": "Sentry", "sentry-sdk": "Sentry",
    "resend": "Resend (email)", "postmark": "Postmark (email)", "mailgun.js": "Mailgun (email)",
    "@slack/web-api": "Slack API", "@octokit/rest": "GitHub API", "paypal-checkout-sdk": "PayPal",
    "@paypal/checkout-server-sdk": "PayPal", "algoliasearch": "Algolia", "@aws-sdk/client-s3": "AWS S3",
    "boto3": "AWS SDK (boto3)", "google-cloud-storage": "Google Cloud Storage",
}

# Hosted services that replace something the team would otherwise run itself.
# (package or env-var prefix) -> (name, category). Category "database"/"cache"/"auth"/"storage"/"email"/"errors"/"search".
MANAGED_SERVICES = {
    "@supabase/supabase-js": ("Supabase", "database"), "@supabase/ssr": ("Supabase", "database"),
    "supabase": ("Supabase", "database"),
    "firebase": ("Firebase", "database"), "firebase-admin": ("Firebase", "database"),
    "firebase_admin": ("Firebase", "database"), "cloud_firestore": ("Firebase", "database"),
    "@planetscale/database": ("PlanetScale", "database"), "@neondatabase/serverless": ("Neon", "database"),
    "@vercel/postgres": ("Vercel Postgres", "database"), "@vercel/kv": ("Vercel KV", "cache"),
    "@upstash/redis": ("Upstash Redis", "cache"), "upstash-redis": ("Upstash Redis", "cache"),
    "@libsql/client": ("Turso (libSQL)", "database"), "convex": ("Convex", "database"),
    "mongodb-atlas": ("MongoDB Atlas", "database"), "@clerk/nextjs": ("Clerk", "auth"),
    "auth0": ("Auth0", "auth"), "@auth0/nextjs-auth0": ("Auth0", "auth"),
    "@aws-sdk/client-s3": ("AWS S3", "storage"), "@aws-sdk/client-dynamodb": ("AWS DynamoDB", "database"),
    "google-cloud-storage": ("Google Cloud Storage", "storage"), "google-cloud-firestore": ("Firestore", "database"),
    "azure-storage-blob": ("Azure Blob Storage", "storage"), "@azure/cosmos": ("Azure Cosmos DB", "database"),
    "@sentry/nextjs": ("Sentry", "errors"), "@sentry/node": ("Sentry", "errors"), "sentry-sdk": ("Sentry", "errors"),
    "algoliasearch": ("Algolia", "search"), "resend": ("Resend", "email"), "@sendgrid/mail": ("SendGrid", "email"),
}
MANAGED_ENV_PREFIXES = {
    "SUPABASE_": ("Supabase", "database"), "NEXT_PUBLIC_SUPABASE_": ("Supabase", "database"),
    "FIREBASE_": ("Firebase", "database"), "NEXT_PUBLIC_FIREBASE_": ("Firebase", "database"),
    "PLANETSCALE_": ("PlanetScale", "database"), "NEON_": ("Neon", "database"),
    "UPSTASH_": ("Upstash", "cache"), "TURSO_": ("Turso (libSQL)", "database"),
    "MONGODB_ATLAS_": ("MongoDB Atlas", "database"), "CONVEX_": ("Convex", "database"),
}


def detect_managed_services(dependency_names, env_var_names=()):
    """Hosted services the app depends on. Names/categories only; found via packages or env-var NAMES."""
    found = {}
    for dep in dependency_names:
        hit = MANAGED_SERVICES.get(dep)
        if hit:
            found[hit[0]] = {"name": hit[0], "category": hit[1], "evidence": "dependency"}
    for env in env_var_names:
        for prefix, (name, cat) in MANAGED_ENV_PREFIXES.items():
            if env.startswith(prefix) and name not in found:
                found[name] = {"name": name, "category": cat, "evidence": "env var name"}
    return sorted(found.values(), key=lambda x: (x["category"], x["name"]))


ENTRYPOINT_CANDIDATES = [
    "main.py", "manage.py", "app.py", "server.py",
    "index.js", "server.js", "app.js",
    "index.mjs", "server.mjs", "app.mjs", "main.mjs",
    "index.cjs", "server.cjs", "app.cjs", "main.cjs",
    "main.go", "Program.cs", "Main.java", "Application.java",
    "index.ts", "main.ts", "server.ts", "app.ts",
]

CONFIG_FRAMEWORK_MARKERS = (
    "BaseSettings",          # pydantic / pydantic-settings
    "from decouple import",
    "environ.Env(",  
    "load_dotenv(",                # django-environ
    "from dotenv import",
    "require('dotenv')",
    'require("dotenv")',
)
ENV_VAR_CODE_PATTERN = re.compile(
    r"(?:process\.env\.([A-Z0-9_]+))|(?:os\.(?:environ(?:\.get)?|getenv)\(['\"]([A-Z0-9_]+)['\"]\))"
    r"|(?:(?:os\.Getenv|System\.getenv|Environment\.GetEnvironmentVariable|getenv|std::env::var|env::var)\(\s*\"([A-Z0-9_]+)\")"
    r"|(?:ENV\[['\"]([A-Z0-9_]+)['\"]\])|(?:ENV\.fetch\(['\"]([A-Z0-9_]+)['\"])"
    r"|(?:os\.environ\[['\"]([A-Z0-9_]+)['\"]\])"
)
CODE_EXTENSIONS = (".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".java", ".kt", ".cs", ".rb", ".php", ".rs")
SKIP_TEXT_SUFFIXES = (".tt", ".j2", ".jinja", ".tmpl", ".tpl", ".lock", ".min.js", ".map", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip",
                      ".gz", ".tar", ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".mp3", ".wasm", ".jar", ".class",
                      ".so", ".dll", ".exe", ".bin", ".pyc", ".lockb", ".po", ".pot", ".xlf", ".csv", ".tsv", ".mo", ".patch", ".diff", ".snap", ".lock")
SKIP_TEXT_NAMES = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "go.sum", "Cargo.lock",
                   "composer.lock", "Gemfile.lock", "uv.lock")
ENV_EXAMPLE_NAMES = (".env.example", ".env.sample", ".env.template", ".env.dist", "example.env", "sample.env")
SENSITIVE_NAME_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".tfstate", ".tfvars", ".ppk")
SENSITIVE_NAMES = ("id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "credentials.json", ".htpasswd", ".pgpass",
                   "kubeconfig", ".pypirc", "terraform.tfstate")
MAX_SECRET_SCAN_BYTES = 300_000
MAX_TEST_FILES_SCANNED = 1500

ENV_VAR_EXAMPLE_PATTERN = re.compile(r"^([A-Z0-9_]+)\s*=")


def detect_entrypoints(repo_path):
    found = []
    for root, dirs, files in walk_repo(repo_path):
        for candidate in ENTRYPOINT_CANDIDATES:
            if candidate in files:
                found.append(os.path.relpath(os.path.join(root, candidate), repo_path))
    return found


def _location_kind(rel):
    low = rel.replace("\\", "/").lower()
    parts = low.split("/")
    if low.startswith(".github/") and not low.endswith((".yml", ".yaml")) and not parts[-1].startswith("."):
        return "test_or_example"          # a key or data file next to the workflows is a CI test fixture, not a leaked credential
    if low.startswith(".github/") or ".circleci" in parts or low.endswith((".gitlab-ci.yml", "jenkinsfile")):
        return "ci"
    if any(p in ("test", "tests", "__tests__", "testing", "e2e", "fixtures", "testdata", "spec", "specs",
                 "example", "examples", "sample", "samples", "docs", "doc", "mock", "mocks", "__mocks__", "t", "dev-docs",
                 "documentation", "demo", "demos", "suites", "integration", "test_resources", "testing-data", ".docker", "testutils", "testutil", "test-utils", "test_utils", "testdata", "devenv", "templates", "quality", "snippets", "bdd", "cypress", "__snapshots__") or p.startswith(("mock", "test_", "test-", "testutil")) or p.endswith(("_test", "_tests", "-test", "-tests")) for p in parts[:-1]) \
            or ".test." in parts[-1] or ".spec." in parts[-1] or "_test." in parts[-1] or parts[-1] in ("mint.json", "docs.json") or parts[-1].endswith((".md", ".mdx", ".rst", ".txt", ".markdoc")) \
            or parts[-1].startswith(("vitest.", "jest.", "playwright.", "cypress.")) or "example" in parts[-1] \
            or "sample" in parts[-1] or "test" in parts[-1] or "mock" in parts[-1] or "fixture" in parts[-1] or ".stories." in parts[-1]:
        return "test_or_example"
    return "source"


def _is_env_file(name):
    if name.endswith((".example", ".sample", ".template", ".dist")):
        return False
    return name == ".env" or (name.startswith(".env.") and name not in ENV_EXAMPLE_NAMES)


def detect_env_vars_and_secrets(repo_path):
    """Env var NAMES only, never values. Real .env files are never opened at all.
    Secret patterns are checked in EVERY text file (any extension, <1 MB). Findings carry
    only the file, the pattern type and where it sits (source / test_or_example / ci) -- never the text."""
    env_vars = set()
    secrets_findings = []
    uses_config_framework = False
    tests_scanned = 0
    hits_in_tests = False
    ignored = GitIgnore(repo_path)

    for root, dirs, files in walk_repo(repo_path):
        for f in files:
            if _is_env_file(f):
                continue  # never open a real env file
            if ignored.active and os.path.relpath(os.path.join(root, f), repo_path) in ignored:
                continue  # git ignores it: it is on this disk, not in the repository
            if f.endswith(SKIP_TEXT_SUFFIXES) or f in SKIP_TEXT_NAMES:
                continue
            full_path = os.path.join(root, f)
            try:
                if os.path.getsize(full_path) > MAX_SECRET_SCAN_BYTES:
                    continue
                with open(full_path, "rb") as fh:
                    raw = fh.read()
            except (IOError, OSError):
                continue
            if b"\0" in raw[:2000]:
                continue
            content = raw.decode("utf-8", "ignore")
            rel = os.path.relpath(full_path, repo_path)
            is_code_file = f.endswith(CODE_EXTENSIONS)
            is_env_example = f in ENV_EXAMPLE_NAMES

            if is_env_example:
                for line in content.splitlines():
                    match = ENV_VAR_EXAMPLE_PATTERN.match(line.strip())
                    if match:
                        env_vars.add(match.group(1))
            if is_code_file:
                for match in ENV_VAR_CODE_PATTERN.finditer(content):
                    name = next((g for g in match.groups() if g), None)
                    if name:
                        env_vars.add(name)
                if any(marker in content for marker in CONFIG_FRAMEWORK_MARKERS):
                    uses_config_framework = True
            if not is_env_example:
                kind = _location_kind(rel)
                if kind == "test_or_example":
                    # a few hundred test files are enough to say "secret-shaped values exist in tests"; Odoo has 40,000 and took a minute
                    tests_scanned += 1
                    if tests_scanned > MAX_TEST_FILES_SCANNED and (hits_in_tests or tests_scanned > 3 * MAX_TEST_FILES_SCANNED):
                        continue
                for finding in scan_text_for_secrets(content):
                    if kind == "test_or_example":
                        hits_in_tests = True
                    secrets_findings.append({"file": rel, "pattern_type": finding["pattern_type"],
                                             "location_kind": "test_or_example" if finding.get("in_comment") else kind})

    return sorted(env_vars), secrets_findings, uses_config_framework


def _looks_like_pem(path):
    """A .key/.pem only counts if it really starts like a PEM file (Apple Keynote files are also .key)."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(80)
            if b"PUBLIC KEY" in head or b"-----BEGIN CERTIFICATE" in head or b"-----BEGIN PUBLIC KEY" in head or b"-----BEGIN X509" in head or b"-----BEGIN DH PARAMETERS" in head or b"-----BEGIN DSA PARAMETERS" in head or b"-----BEGIN EC PARAMETERS" in head:
                return False                  # certificates and public keys are meant to be public (DigiCert root, CA bundles)
            return b"-----BEGIN" in head
    except OSError:
        return False


def _is_empty(path):
    try:
        return os.path.getsize(path) == 0
    except OSError:
        return True


def detect_sensitive_files(repo_path):
    """File NAMES only. Committed .env files and key/state files are a finding by themselves,
    even though the scanner never opens them."""
    env_files, dev_env_files, sensitive = [], [], []
    gitignore = ""
    try:
        with open(os.path.join(repo_path, ".gitignore"), "r", errors="ignore") as fh:
            gitignore = fh.read()
    except (IOError, OSError):
        pass
    ignores_env = bool(re.search(r"(?m)^\s*/?\.env(\*|\.\*)?\s*$", gitignore))
    ignored = GitIgnore(repo_path)
    for root, dirs, files in walk_repo(repo_path):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), repo_path)
            if ignored.active and rel in ignored:
                continue          # present on disk but ignored by git: not committed
            if _is_env_file(f) and f not in ENV_EXAMPLE_NAMES:
                if _location_kind(rel) == "source":
                    if f.lower().endswith((".test", ".development", ".dev", ".vagrant", ".ci", ".local", ".e2e")):
                        dev_env_files.append(rel)
                    else:
                        env_files.append(rel)
            elif _is_empty(os.path.join(root, f)) or (f.endswith((".key", ".pem")) and
                                                     not _looks_like_pem(os.path.join(root, f))):
                continue
            elif f in SENSITIVE_NAMES or f.endswith(SENSITIVE_NAME_SUFFIXES) or \
                    (f.startswith("service-account") and f.endswith(".json")):
                if f.endswith(".tfvars") and ("example" in f or "sample" in f):
                    continue
                sensitive.append({"file": rel, "location_kind": _location_kind(rel)})
    return {
        "env_files": sorted(env_files)[:20],
        "dev_env_files": sorted(dev_env_files)[:20],
        "env_ignored_by_gitignore": ignores_env,
        "sensitive_file_names": sorted(sensitive, key=lambda x: x["file"])[:30],
    }


def detect_third_party_services(dependency_names):
    return [THIRD_PARTY_PACKAGES[name] for name in dependency_names if name in THIRD_PARTY_PACKAGES]


def detect_monorepo(repo_path):
    manifest_locations = []
    for root, dirs, files in walk_repo(repo_path):
        if any(f in ("package.json", "requirements.txt", "pyproject.toml", "go.mod", "pom.xml",
                     "build.gradle", "build.gradle.kts", "Cargo.toml") or f.endswith(".csproj")
               for f in files):
            manifest_locations.append(os.path.relpath(root, repo_path) or ".")
    return {
        "is_monorepo": len(manifest_locations) > 1,
        "manifest_locations": manifest_locations,
    }
