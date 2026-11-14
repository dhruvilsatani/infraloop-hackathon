"""Hand-applied fixes for gaps about files the repository ALREADY has.

The generator never edits an existing file, so for these gaps it writes exact steps (and a snippet where one helps) into MANIFEST.md.
Every entry is a fixed template: no AI model, no source code read. The gap's own detail from the scan is quoted as "Found"."""
from .model import Advice

_UNTRACK = ["Open each file listed under Found and decide whether it holds real credentials. InfraLoop did not read them.",
            "Stop tracking it without deleting your local copy, and make git ignore it from now on (replace the placeholder):",
            "Anything that was ever real in that file is still in your git history. Rotate those secrets: removing the file does not undo it.",
            "Commit a template with names only (a .env.example) so others know what to set."]
_UNTRACK_CODE = "git rm --cached <file>\necho \"<file>\" >> .gitignore\ngit commit -m \"Stop tracking <file>\""

ADVICE = {
    "containers_run_as_root": (
        "Run the container as a non-root user",
        ["Add these lines to each Dockerfile listed under Found, after the dependencies are installed and before CMD (Debian or Ubuntu based image):",
         "On Alpine use `RUN adduser -D -u 10001 app` instead of `useradd`. The official node images already have a user called `node`: use `USER node`.",
         "Check that the app can still read its files and only writes where it must (a data or temp folder)."],
        "RUN useradd --create-home --uid 10001 app\nUSER app", "dockerfile"),
    "unpinned_base_images": (
        "Pin the base image version",
        ["Replace the bare image name in `FROM` with a specific version, for example `FROM python:3.12-slim` instead of `FROM python`.",
         "For fully reproducible builds pin the digest: run `docker pull <image>:<tag>`, then `docker inspect --format '{{index .RepoDigests 0}}' <image>:<tag>`, and use that value in `FROM`.",
         "Dependabot (docker ecosystem) can open pull requests when a newer tag exists."], None, ""),
    "ci_does_not_run_tests": (
        "Make CI run your tests",
        ["Add a step that runs your test command before any build or deploy step. The job must fail when a test fails.",
         "Example for GitHub Actions; use the command your project already uses:"],
        "- run: python -m pytest      # or: npm test   /   go test ./...", "yaml"),
    "ci_does_not_build_images": (
        "Build the image in CI",
        ["Add a build step so a broken Dockerfile is caught before a deploy, not during it:"],
        "- run: docker build -t app:ci .", "yaml"),
    "ci_no_security_scanning": (
        "Add dependency and code scanning",
        ["Turn on dependency alerts and code scanning in your repository's security settings, or the equivalent in your CI host.",
         "Add an image or dependency scan step once your build is stable. Pin any third-party action to a full commit SHA, not a tag."], None, ""),
    "env_file_in_repo": ("Stop committing environment files", _UNTRACK, _UNTRACK_CODE, "bash"),
    "dev_env_files_in_repo": ("Check the committed development env files", _UNTRACK, _UNTRACK_CODE, "bash"),
    "sensitive_files_in_repo": ("Remove key and state files from the repository", _UNTRACK, _UNTRACK_CODE, "bash"),
    "tfvars_file_in_repo": ("Stop committing Terraform variable files", _UNTRACK, _UNTRACK_CODE, "bash"),
    "terraform_no_lock_file": (
        "Commit the Terraform provider lock file",
        ["Run `terraform init` in each Terraform folder, then commit the `.terraform.lock.hcl` file it creates.",
         "Do not put `.terraform.lock.hcl` in .gitignore."], None, ""),
    "terraform_no_remote_state": (
        "Move Terraform state to a remote backend",
        ["Pick a remote backend that supports locking (for example an object-storage bucket with locking, or Terraform Cloud). Which one depends on your cloud, so InfraLoop does not guess.",
         "Add a `backend` block, then run `terraform init -migrate-state`. Make sure nobody runs Terraform while you migrate."], None, ""),
    "k8s_images_use_latest_tag": (
        "Stop using the latest image tag in Kubernetes",
        ["Replace `:latest` (or a missing tag) in every container image with a specific version or digest, so a rollout always runs what you tested."], None, ""),
    "k8s_no_security_context": (
        "Add a security context to your workloads",
        ["Add this under each container in the pod spec:",
         "`runAsNonRoot` only works if the image has a non-root user (see the Dockerfile fix). Test in a non-production namespace first: some images fail when they cannot write to the filesystem."],
        "securityContext:\n  runAsNonRoot: true\n  allowPrivilegeEscalation: false\n  capabilities:\n    drop: [\"ALL\"]", "yaml"),
    "no_health_probes": (
        "Add health probes",
        ["Your app needs a cheap endpoint that answers when it can serve requests (for example `/health`). That is a code change InfraLoop cannot make.",
         "Then add probes to each container in your manifests (replace the placeholder port):"],
        "readinessProbe:\n  httpGet: {path: /health, port: <port>}\nlivenessProbe:\n  httpGet: {path: /health, port: <port>}", "yaml"),
    "no_dependency_lockfile": (
        "Create and commit a lock file",
        ["Run your package manager once and commit the file it creates:",
         "Python: `pip-compile` (pip-tools) or `poetry lock`. Node: `npm install` creates package-lock.json. Go: `go mod tidy` creates go.sum.",
         "Then switch CI and the Dockerfile to the locked install (`npm ci`, `pip install -r requirements.txt` from the compiled file)."], None, ""),
}


def advice_for(issue, gap):
    if issue not in ADVICE:
        return None
    title, steps, snippet, lang = ADVICE[issue]
    return Advice(gap=issue, title=title, found=(gap or {}).get("detail", ""), steps=list(steps), snippet=snippet or "", snippet_lang=lang)
