# Commit readiness checklist

Mark each applicable item PASS, FAIL, or NOT CHECKED and attach evidence.
Use N/A with a reason when the change does not affect an item. A scanner pass
alone is insufficient for READY. A known failure blocks readiness; missing
required evidence needs review.

## Scope and Git state

- [ ] Read applicable agent rules and the user's intended change.
- [ ] Inventory staged, unstaged, untracked, deleted, and renamed files.
- [ ] Review the exact staged content as well as working files; identify mixed versions.
- [ ] Keep unrelated edits out of the proposed commit; specify filenames for staging.
- [ ] Resolve merge/rebase/cherry-pick state, unmerged index entries, and conflict markers.
- [ ] Check whitespace errors; review executable bits, symlinks, and submodules.
- [ ] Recheck after tests or edits; state that the verdict applies only to this snapshot.

## Secrets and private data

- [ ] No private keys, API tokens, credentials, passwords, authenticated URLs, or signing material in changed content, including staged blobs and new files.
- [ ] No real credentials in examples, recordings, tests, logs, notebooks, screenshots, archives, or generated assets. Template names do not exempt their content.
- [ ] No credential stores, local environment files, cloud credentials, personal configuration, or private databases in the proposed commit.
- [ ] Secret reports redact values; exceptions are inspected and explained, never silently suppressed.
- [ ] If a real key was exposed, flag revocation/rotation; removal alone is insufficient.
- [ ] Review binary, oversized, skipped, ignored, and submodule coverage explicitly. Use a vetted local scanner if available; do not install tools or transmit source without authorization.
- [ ] State that heuristic scanning cannot recognize all secrets or audit existing history.

## Security of the code change

- [ ] Check authorization, authentication, tenant boundaries, and permission changes.
- [ ] Validate input at trust boundaries; check injection, shell execution, unsafe deserialization, path traversal, SSRF, and redirects where relevant.
- [ ] Check sensitive logging, exception messages, error disclosure, and personal data handling.
- [ ] Review cryptography, TLS verification, token lifetime, and secure defaults where changed.
- [ ] Inspect dependencies, lockfiles, scripts, hooks, CI permissions, and newly introduced install/build commands. Run configured audits when applicable and available; flag missing evidence.
- [ ] Check migration/destructive behavior, resource limits, retries, concurrency, and billing side effects where relevant.

## Correctness and maintainability

- [ ] Verify behavior against the task, including edge cases and failure paths.
- [ ] Review API compatibility, schemas, defaults, config, migrations, and generated interfaces.
- [ ] No accidental debug code, temporary overrides, disabled validation, or unjustified test skips.
- [ ] No unrelated refactors or generated/vendor/build/cache files without a reason.
- [ ] Documentation matches changed behavior; project conventions and required cross-file updates hold.
- [ ] Tests exercise behavior and would fail if the fix were removed.

## Validation and handoff

- [ ] Required project tests, convention checks, and relevant lint/type/build checks pass.
- [ ] Test the version being proposed for commit; worktree tests do not establish staged-version correctness.
- [ ] Record commands, results, failures, and unavailable checks without fabricating success.
- [ ] Verify tests leave no unexpected artifacts or edits; rerun the local scanner.
- [ ] Give a verdict with evidence and remaining gaps, then exact commands for the user.
- [ ] Leave staging unchanged during review; never commit, push, or rewrite history.
