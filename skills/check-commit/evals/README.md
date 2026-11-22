# Evaluations

`python3 ../scripts/run_evals.py` runs offline integration tests from any working
directory when the script is invoked by its full path. Fresh temporary Git
repositories are removed automatically. No commits or network requests occur.

`evals.json` defines two agent tasks, each run once with this skill and once
without it. The first uses staged synthetic credential content with a cleaned
working copy and an untracked README. The second stages a greeting helper, one
behavioral unittest, a README documenting the test command, and cache ignore rules.
Use separate fresh fixtures for each variant. Agents must preserve source/index
and write their review outside the fixture. These are examples, not exhaustive
coverage of agent behavior.

Saved runs are in the sibling `check-commit-workspace/iteration-1` directory.
Each run contains a fixture, original file/index snapshots, an `outputs/report.md`,
and `grading.json`. Snapshots can contain synthetic credentials and must stay out
of the viewer output directory. No real credentials are used.

Regrade the retained runs with:

```sh
python3 <skill-directory>/scripts/grade_evals.py <workspace>/iteration-1
```

The grader checks verdict/evidence in reports, redaction against the staged
synthetic credential, source/index preservation, and the absence of a HEAD
commit. It does not verify hidden execution transcripts or prove that a push
was never attempted. The runner did not provide token or timing measurements;
do not infer performance improvement from these runs.
