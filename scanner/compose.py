"""Tiny docker-compose reader (no YAML library needed). Only the keys we care about:
service name, image, whether it has a build step, whether it mounts a volume."""
import re

SERVICE_NAME_RE = re.compile(r"^  ([\w.\-]+):\s*$")


def is_compose_filename(name):
    return bool(re.match(r"(docker-)?compose.*\.ya?ml$", name, re.IGNORECASE))


def parse_compose(text):
    services, cur, in_services = {}, None, False
    svc_indent = field_indent = None
    for line in text.splitlines():
        if re.match(r"^services:\s*$", line):
            in_services, cur, svc_indent, field_indent = True, None, None, None
            continue
        if in_services and re.match(r"^\S", line) and not line.startswith("#"):
            in_services = False
        if not in_services or not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if svc_indent is None:
            svc_indent = indent
        if indent == svc_indent:
            m = re.match(r"^\s*([\w.\-]+):\s*(?:#.*)?$", line)
            if m:
                cur = m.group(1)
                services[cur] = {"image": "", "build": False, "volumes": False}
                field_indent = None
            continue
        if cur is None or indent <= svc_indent:
            continue
        if field_indent is None:
            field_indent = indent
        if indent != field_indent:
            continue
        stripped = line.strip()
        if stripped.startswith("image:"):
            services[cur]["image"] = stripped.split(":", 1)[1].strip().strip("\"'")
        elif re.match(r"build\b", stripped):
            services[cur]["build"] = True
        elif stripped.startswith("volumes:"):
            services[cur]["volumes"] = True
    return services
