"""Dockerfile and .dockerignore templates. Written by code from scan facts only: the same scan gives the same files."""
from .model import Artifact, HEADER
from .registry import generator
from .context import services, join, where

BASE_NOTE = "Base image tags (python:3.12-slim, node:22-slim, golang:1.25) were chosen when this template was written: check that they are still supported."

COMMON_IGNORE = [".git", ".gitignore", ".env", ".env.*", "!.env.example", "*.pem", "*.key", ".vscode", ".idea", ".DS_Store",
                 "Dockerfile", ".dockerignore", "docker-compose*.yml", "*.md", "tests", ".github"]
KIND_IGNORE = {
    "python": ["__pycache__", "*.pyc", ".venv", "venv", ".pytest_cache", ".mypy_cache", "*.egg-info"],
    "node": ["node_modules", "npm-debug.log", "coverage"],
    "go": ["bin", "*.test", "*.out"],
}


def _python(s):
    fw = set(s.frameworks)
    stem = s.entrypoint[:-3].replace("/", ".") if s.entrypoint.endswith(".py") else ""
    assume = ["Dependencies are installed from requirements.txt in this folder.", "The app listens on port 8000."]
    review = [BASE_NOTE]
    conf = "medium"
    if s.entrypoint.endswith("manage.py") or "django" in fw:
        cmd = '["gunicorn", "--bind", "0.0.0.0:8000", "YOUR_PROJECT.wsgi:application"]'
        review += ["Replace YOUR_PROJECT with the name of your Django project package.", "Add gunicorn to requirements.txt."]
        conf = "low"
    elif {"fastapi", "starlette"} & fw and stem:
        cmd = f'["python", "-m", "uvicorn", "{stem}:app", "--host", "0.0.0.0", "--port", "8000"]'
        assume.append(f"The FastAPI object is called `app` and lives in {s.entrypoint}.")
        if "uvicorn" not in fw:
            review.append("Add uvicorn to requirements.txt.")
    elif "flask" in fw and stem:
        cmd = f'["gunicorn", "--bind", "0.0.0.0:8000", "{stem}:app"]'
        assume.append(f"The Flask object is called `app` and lives in {s.entrypoint}.")
        review.append("Add gunicorn to requirements.txt.")
    elif s.entrypoint:
        cmd = f'["python", "{s.entrypoint}"]'
        assume.append(f"The app starts by running {s.entrypoint}.")
        conf = "low"
    else:
        cmd = '["python", "REPLACE_WITH_YOUR_ENTRYPOINT.py"]'
        review.append("The scan found no entry point: replace the CMD with the command that starts your app.")
        conf = "low"
    body = f"""FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --uid 10001 --create-home app && chown -R app /app
USER app
EXPOSE 8000
# HEALTHCHECK: add one once you know a route that answers when the app is healthy.
CMD {cmd}
"""
    review.append("If you use pyproject.toml, poetry or pipenv instead of requirements.txt, change the two install lines.")
    return body, assume, review, conf


def _node(s):
    install = "npm ci --omit=dev" if s.lockfile else "npm install --omit=dev"
    assume = ["The app listens on port 3000.", "The start command is `node " + (s.entrypoint or "server.js") + "`."]
    review = [BASE_NOTE, "If package.json has a different start script, or the app needs a build step (TypeScript, a bundler), change the CMD."]
    if not s.lockfile:
        review.append("No lock file was found: commit package-lock.json and switch the install line to `npm ci --omit=dev`.")
    conf = "medium" if s.entrypoint else "low"
    if not s.entrypoint:
        review.append("The scan found no entry point: replace server.js in the CMD with your start file.")
    body = f"""FROM node:22-slim
ENV NODE_ENV=production
WORKDIR /app
COPY package*.json ./
RUN {install}
COPY . .
USER node
EXPOSE 3000
# HEALTHCHECK: add one once you know a route that answers when the app is healthy.
CMD ["node", "{s.entrypoint or 'server.js'}"]
"""
    return body, assume, review, conf


def _go(s):
    body = """FROM golang:1.25 AS build
WORKDIR /src
COPY go.mod go.sum* ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /out/app .

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/app /app
USER nonroot
EXPOSE 8080
# HEALTHCHECK: distroless has no shell; use the health check of your platform instead.
ENTRYPOINT ["/app"]
"""
    return body, ["The main package is in the root of this folder (`go build .`).", "The app listens on port 8080."], \
        [BASE_NOTE, "Match the golang version to the one in go.mod.", "If your main package is in cmd/<name>, change the build line."], "medium"


_BUILD = {"python": _python, "node": _node, "go": _go}


def _commented(text):
    return "".join(f"# {line}\n" for line in text.splitlines())


@generator("no_dockerfile", "services_without_dockerfile")
def dockerfiles(scan, gaps):
    """A Dockerfile for every service folder that has none. Folders that already have one are never touched."""
    svcs, _ = services(scan)
    gap = "no_dockerfile" if "no_dockerfile" in {g["issue"] for g in gaps} else "services_without_dockerfile"
    out = []
    for s in svcs:
        if s.has_dockerfile:
            continue
        body, assume, review, conf = _BUILD[s.kind](s)
        out.append(Artifact(path=join(s.path, "Dockerfile"), content=_commented(HEADER) + body, gap=gap,
                            title=f"Dockerfile for the {s.kind} service in {where(s.path)}", confidence=conf, assumptions=assume,
                            review=review + ["Build it from this folder: docker build -t app ."]))
    return out


@generator("no_dockerfile", "services_without_dockerfile", "no_dockerignore")
def dockerignores(scan, gaps):
    """One .dockerignore next to every Dockerfile that is generated, or that exists without one."""
    svcs, _ = services(scan)
    issues = {g["issue"] for g in gaps}
    out = []
    for s in svcs:
        if s.has_dockerfile and "no_dockerignore" not in issues:
            continue
        if not s.has_dockerfile and not ({"no_dockerfile", "services_without_dockerfile"} & issues):
            continue
        lines = COMMON_IGNORE + KIND_IGNORE.get(s.kind, [])
        out.append(Artifact(path=join(s.path, ".dockerignore"), content=_commented(HEADER) + "\n".join(lines) + "\n",
                            gap="no_dockerignore" if "no_dockerignore" in issues else ("no_dockerfile" if "no_dockerfile" in issues else "services_without_dockerfile"),
                            title=f".dockerignore for {where(s.path)}", confidence="high",
                            assumptions=["Tests, markdown files and CI config are not needed inside the image."],
                            review=["If your app reads a file that is listed here (for example a README at runtime), remove that line."]))
    return out
