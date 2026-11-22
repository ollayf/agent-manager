#!/usr/bin/env python3
"""Render a ${VAR} template using values from an env file.

    render.py <template> <env-file> <output>

Output is written 0600. A missing variable is a hard error — a half-rendered
credentials file that silently contains the literal "${GLM_ZAI_TOKEN}" would
fail at runtime in a much more confusing way.
"""
import os
import re
import sys

VAR = re.compile(r"\$\{([A-Z0-9_]+)\}")


def load_env(path):
    env = {}
    with open(path) as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if key.startswith("export "):
                key = key[len("export "):].strip()
            env[key] = val.strip().strip('"').strip("'")
    return env


def main():
    tpl, envfile, out = sys.argv[1:4]
    env = load_env(envfile)
    text = open(tpl).read()

    missing = sorted({m for m in VAR.findall(text) if m not in env})
    if missing:
        sys.exit(
            f"render.py: {os.path.basename(envfile)} is missing: {', '.join(missing)}"
        )

    rendered = VAR.sub(lambda m: env[m.group(1)], text)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(rendered)


if __name__ == "__main__":
    main()
