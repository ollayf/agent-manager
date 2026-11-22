#!/usr/bin/env python3
"""Check the common campaign policy shape and contained, disjoint paths."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("policy", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    schema = json.loads((Path(__file__).resolve().parents[1] / "references" / "policy.schema.json").read_text(encoding="utf-8"))
    try:
        import jsonschema
    except ImportError:
        # The core checks below use only the standard library. The full JSON
        # Schema is applied when jsonschema is installed in the project env.
        required = schema["required"]
        missing = [key for key in required if key not in policy]
        if missing:
            raise ValueError(f"Missing policy fields: {missing}")
    else:
        jsonschema.validate(policy, schema)
    if policy["format_version"] != 1 or not policy["target_agent"].strip() or not policy["goal"].strip():
        raise ValueError("Policy identity or goal is missing")
    files = policy["allowed_iteration_files"]
    reserved = {"iteration.json", "analysis.json", "metrics.json"}
    if not files or len(set(files)) != len(files) or reserved & set(files):
        raise ValueError("Allowed iteration files are empty, duplicated, or include fixed metadata")
    if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name) for name in files):
        raise ValueError("Allowed iteration files must be basenames")
    keys = policy["metric_keys"]
    if not keys or len(set(keys)) != len(keys):
        raise ValueError("Metric keys are empty or duplicated")
    if policy["analysis"]["source_split"] != "train" or not policy["analysis"]["required_before_child"]:
        raise ValueError("Child analysis must use training failures")

    def inside(value: str) -> Path:
        candidate = Path(value)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError(f"Path must be repository-relative: {value}")
        path = (repo / candidate).resolve()
        try:
            path.relative_to(repo)
        except ValueError:
            raise ValueError(f"Path escapes repository: {value}")
        return path

    inputs = [inside(policy["datasets"][key]) for key in ("train", "eval", "manifest")]
    if len(set(inputs)) != len(inputs):
        raise ValueError("Train, eval, and manifest paths must differ")
    if "held_out" in policy["datasets"]:
        inputs.append(inside(policy["datasets"]["held_out"]))
    for key, value in policy["fixed"].items():
        if key == "shared_library":
            inputs.extend(inside(item) for item in value)
        elif isinstance(value, str):
            inputs.append(inside(value))
    for key, value in policy["paths"].items():
        path = inside(value)
        if key.startswith("baseline_"):
            inputs.append(path)
    missing = [str(path) for path in inputs if not path.is_file()]
    if missing:
        raise ValueError(f"Fixed inputs are missing: {missing}")
    outputs = [inside(policy["paths"][key]) for key in ("iterations", "analyses", "best", "outputs")]
    if len(set(outputs)) != len(outputs) or any(path in inputs for path in outputs):
        raise ValueError("History/output paths overlap each other or fixed inputs")
    print(f"Valid policy: {policy['target_agent']}; {len(keys)} metrics; {len(files)} mutable files")


if __name__ == "__main__":
    main()
