#!/usr/bin/env python3
"""Report file-type warnings for every addition, including staged blobs.

Shares inventory and bounded classification with check_worktree.py. This is
file hygiene only: use the full checker for secrets and other commit checks.
"""
import argparse
import json
import sys
from check_worktree import check, CheckError


def added_report(report):
    files = [record for record in report["file_checks"] if record["added"]]
    paths = {record["path"] for record in files}
    warnings = [dict(warning, path=record["path"], source=record["source"],
                     category=record["category"], size_bytes=record["size_bytes"])
                for record in files for warning in record["warnings"]]
    # Include read/coverage failures and races, never claim a partial check passed.
    for finding in report["findings"]:
        if (finding.get("path") in paths and finding["code"] in {
                "oversized-not-scanned", "unreadable-not-scanned", "symlink-parent-not-scanned",
                "nonregular-not-scanned", "submodule-not-scanned", "binary-not-scanned", "encoding-not-scanned"}
                or finding["code"] in {"worktree-changed-during-check", "added-file-not-inspected",
                                        "added-files-total-size-review"}):
            warnings.append({"reason": "File contents were skipped or the repository changed during inspection.",
                             "action": "Review the stated coverage gap; resolve read/race errors and rerun before judging readiness.",
                             **finding})
        elif finding["code"] == "case-collision-review":
            warnings.append(finding)
    return {"status": "NEEDS_REVIEW" if warnings else "AUTOMATED_PASS",
            "repository": report["repository"], "summary": report["added_file_summary"],
            "files": files, "warnings": warnings,
            "limitations": ["Only pending added files are covered; ignored untracked files are excluded.",
                            "Renamed destinations are treated as additions for this inspection.",
                            "Headers and extensions do not identify every format or inspect embedded contents.",
                            "No files are executed, opened in applications, deserialized, or extracted.",
                            "This is file hygiene only; run check_worktree.py for secret and commit checks."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        report = added_report(check(args.repo))
    except (CheckError, OSError, ValueError):
        report = {"status": "NEEDS_REVIEW", "files": [], "warnings": [
            {"severity": "review", "code": "operational-error",
             "reason": "Could not complete added-file inventory or inspection.",
             "action": "Resolve repository/object access and rerun."}], "limitations": [
                 "Coverage is incomplete; no readiness verdict is available."]}
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=True))
    else:
        print(report["status"])
        for record in report["files"]:
            print(json.dumps({k: record[k] for k in ("path", "source", "size_bytes", "category", "detected_format", "inspection")}, ensure_ascii=True))
        for warning in report["warnings"]:
            print(json.dumps(warning, ensure_ascii=True))
        for limitation in report["limitations"]:
            print(limitation)
    return 2 if report["status"] == "NEEDS_REVIEW" else 0


if __name__ == "__main__":
    sys.exit(main())
