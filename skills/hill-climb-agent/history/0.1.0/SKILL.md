---
name: hill-climb-agent
description: Set up a reproducible hill-climb skill for a named agent and goal, with fixed datasets, metrics, parent selection, failure analysis, and a restricted mutation surface. Use for setup or redesign, not for running an existing campaign.
metadata:
  skill_version: "0.1.0"
---

# Set up an agent hill climb

Inspect the target repository and any existing agent, evaluator, datasets, and shared runner first. Reuse answered decisions. Interview the user about each unresolved decision in [the question guide](references/questions.md), one question at a time with a recommended answer. Do not silently invent ground truth, permissions, or a costly evaluation budget.

Create one skill for the target agent and one machine-readable `policy.json` conforming to [the policy schema](references/policy.schema.json). Keep the policy beside that skill. The policy names the target and goal, fixed train/eval inputs, metric contract, parent rule, analysis gate, mutation whitelist, and exact history/output paths. Put the campaign implementation in a shared library when more than one skill needs it; do not duplicate scoring or history logic in each skill. The generated skill explains how to run its policy and library, and how to inspect the parent's training failures before creating a child.

Pin fixed inputs by hash before the first score. Each iteration records its parent, policy/input fingerprint, mutable artifact hashes, analysis evidence, model/backend, and metric result. Select parents only from the current best **training** score; define aggregation and tie handling in the fixed contract. Keep eval and holdout data out of parent selection and failure analysis. Never rewrite scored history after a fixed input, metric, or shared-code change; start a new campaign/version. Stamp lasting artifacts with skill and format versions. Run `python3 scripts/validate_policy.py --repo <project-root> <new-skill>/policy.json` after writing the policy.

Permit only the mutation files named in the policy. A backend switch, output-schema edit, or prompt edit is allowed only if that campaign lists it. Require a concrete training-failure observation and testable hypothesis before a child is created. Keep credentials outside artifacts, and make separately billed calls explicit in the run command. Create a dry-run and integrity check, then verify both before saying the campaign is ready. Report any remaining blockers, especially provisional labels or missing datasets. Do not run scoring merely because the setup skill was invoked.

When releasing a generated skill that writes lasting artifacts, freeze its SKILL.md and implementation under `history/<version>/` with SHA256SUMS. Keep readers for past formats, or fall back to the frozen reader that wrote an artifact. Version a changed data layout and provide a resumable migration plan before upgrading it.
