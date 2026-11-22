# Initial validation — 2026-10-05

- 33 offline integration tests passed, including synthetic secrets in the index,
  cleaned working copies, redaction, untracked/ignored files, merge conflicts,
  binary/oversized coverage gaps, symlink handling, unusual filenames, read-only
  behavior, changing inventory, and a disabled-detector mutation guard.
- Two agent scenarios each ran with and without the skill: staged credential
  after working-copy cleanup, and a clean greeting change with documented tests.
  Both variants passed 10/10 report/snapshot assertions. These cases establish
  expected behavior, not superiority over baseline or broad agent reliability.
- Credential redaction and original file/index preservation were independently
  checked. Agent execution claims were graded from reports; full transcripts,
  timing, and token measurements were unavailable.
- Skill frontmatter validated. The target project's required convention checks
  passed: 152 passed, 16 skipped. The skill lives in user scope; the target
  project's source and index were not edited by this task.
- A read-only smoke scan of the target worktree flagged two symlink changes for
  review and an authenticated-URL documentation example for manual triage.
  This was a scanner smoke test, not a full readiness review of those existing edits.

The sibling `check-commit-workspace/iteration-1/review.html` contains the saved
agent reports and assertion results. `benchmark.json` omits unavailable timing
and token data. Rerun `scripts/run_evals.py` to verify the scanner, and use
`scripts/grade_evals.py` to recheck retained agent reports and fixture snapshots.
