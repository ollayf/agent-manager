#!/usr/bin/env python3
"""Losslessly maintain agent-manager's small top-level block in Codex config.toml."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # macOS still ships Python 3.9 on otherwise supported systems.
    tomllib = None

START = "# >>> agent-manager managed defaults >>>"
END = "# <<< agent-manager managed defaults <<<"
ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*=")
TABLE = re.compile(r"^\s*\[\[?.*\]\]?\s*(?:#.*)?$")


def managed_keys(defaults: str) -> set[str]:
    keys: set[str] = set()
    for line in defaults.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if TABLE.match(line):
            raise ValueError("defaults may contain top-level scalars only")
        match = ASSIGNMENT.match(line)
        if not match:
            raise ValueError(f"unsupported defaults line: {line}")
        keys.add(match.group(1))
    return keys


def without_old_block(text: str) -> str:
    pattern = re.compile(
        rf"(?ms)^\s*{re.escape(START)}\n.*?^\s*{re.escape(END)}\n?"
    )
    return pattern.sub("", text)


def strip_owned_root_keys(text: str, keys: set[str]) -> str:
    output: list[str] = []
    in_root = True
    for line in text.splitlines(keepends=True):
        if TABLE.match(line):
            in_root = False
        match = ASSIGNMENT.match(line) if in_root else None
        if match and match.group(1) in keys:
            continue
        output.append(line)
    return "".join(output).lstrip("\n")


def render(current: str, defaults: str) -> str:
    keys = managed_keys(defaults)
    unmanaged = strip_owned_root_keys(without_old_block(current), keys)
    block = f"{START}\n{defaults.rstrip()}\n{END}\n"
    result = block + ("\n" + unmanaged if unmanaged else "")
    if tomllib is not None:
        tomllib.loads(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("defaults", type=Path)
    parser.add_argument("current", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    defaults = args.defaults.read_text()
    current = args.current.read_text() if args.current.exists() else ""
    args.output.write_text(render(current, defaults))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"codex config merge failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
