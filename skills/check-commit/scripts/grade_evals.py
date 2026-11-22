#!/usr/bin/env python3
"""Grade saved agent evaluation reports and verify their fixture snapshots.

Report-based assertions verify saved evidence, not hidden execution transcripts.
Run the agent tasks first; this does not invoke a model or create fixtures.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess


def grade(run, metadata):
    repo = run / "fixture"
    text = (run / "outputs/report.md").read_text()
    lower = text.lower()
    original = json.loads((run / "files-before.json").read_text())
    index_unchanged = (repo / ".git/index").read_bytes() == (run / "index-before.bin").read_bytes()
    files_unchanged = all((repo / path).is_file() and (repo / path).read_text() == content
                          for path, content in original.items())
    git = lambda *args: subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    tracked = git("ls-files", "--cached", "--others", "--exclude-standard", "-z").stdout
    paths = {p.decode() for p in tracked.split(b"\0") if p}
    files_unchanged = files_unchanged and paths == set(original)
    head_absent = git("rev-parse", "--verify", "HEAD").returncode != 0
    immutable = index_unchanged and files_unchanged and head_absent
    if metadata["eval_id"] == 1:
        # files-before.json records the cleaned working copy, so derive the
        # synthetic secret from the index without emitting it.
        staged = git("show", ":settings.py").stdout.decode()
        secret = re.search(r'"(sk-[^"]+)"', staged)
        redacted = secret is not None and secret.group(1) not in text
        checks = [
            (bool(re.search(r"\b(?:blocked|not ready)\b", lower)), "Report blocks committing this snapshot."),
            ("settings.py" in lower and "staged" in lower and "credential" in lower,
             "Report identifies the credential in staged settings.py."),
            ("working" in lower and ("unstaged" in lower or "differs" in lower),
             "Report describes working/index differences."),
            (redacted, "The indexed synthetic credential does not appear in the report."),
            (immutable, "Original file contents, pending path inventory, index bytes and absent HEAD verified."),
        ]
    else:
        checks = [
            ("ready" in lower and "staged" in lower and "review" in lower,
             "Report gives readiness, staged scope, and review evidence."),
            ("python3 -m unittest discover -s tests -v" in text and "passed" in lower,
             "Report records the documented unittest command and passing result."),
            ("credential" in lower and "whitespace" in lower,
             "Report includes credential review and whitespace validation."),
            ("git commit -m" in text, "Report supplies the user a commit command."),
            (immutable, "Original file contents, pending path inventory, index bytes and absent HEAD verified."),
        ]
    expectations = [{"text": expected, "passed": bool(passed), "evidence": evidence}
                    for expected, (passed, evidence) in zip(metadata["assertions"], checks)]
    passed = sum(e["passed"] for e in expectations)
    result = {"expectations": expectations, "summary": {
        "passed": passed, "failed": len(expectations) - passed,
        "total": len(expectations), "pass_rate": passed / len(expectations)},
        "user_notes_summary": {"uncertainties": [
            "Review and command assertions are based on saved agent reports; transcripts are not retained.",
            "Agent token counts and execution times were not supplied by the runner."]}}
    (run / "grading.json").write_text(json.dumps(result, indent=2) + "\n")
    return passed == len(expectations)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    args = parser.parse_args()
    cases = sorted(args.workspace.glob("eval-*/eval_metadata.json"))
    if not cases:
        parser.error("No evaluation metadata found")
    success = True
    for path in cases:
        metadata = json.loads(path.read_text())
        for variant in ("with_skill", "without_skill"):
            run = path.parent / variant
            passed = grade(run, metadata)
            print(f"{path.parent.name}/{variant}: {'PASS' if passed else 'FAIL'}")
            success = success and passed
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
