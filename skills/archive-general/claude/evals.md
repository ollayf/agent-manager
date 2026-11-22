# Rebuild validation — 2026-10-18

Release **2.3.1** rebuilds the system described by the recovered 2.3.0 guide. Both skills share one engine and are installed through the existing shared global skills source for Claude Code and Codex. Appendices A and B were copied with only their version lines changed; Appendix C is unchanged. Appendix D is present in the shared global instructions.

| Check | Result |
|---|---|
| Pytest, final full run | **155 passed, 104 skipped**, 259 collected; 139.82 seconds |
| Original test inventory | All 219 named cases retained: 94 current, 57 folder, 68 legacy |
| Additional rebuild regressions | 40 cases, including literal legacy-format data, interrupted upgrades, import batching, protected index paths, inventory, release immutability, and version agreement |
| Mutation tests | **52 killed, 21 skipped**; all 73 replacement sets match exactly once and parse |
| Independent agent evaluations | **11 passed, 5 skipped** |
| Scorer self-test | All 11 runnable good scripts pass; all 11 corresponding bad scripts fail |
| Swift helper | `swiftc -typecheck` passed; a local file correctly reports `not-icloud` |
| Generated rebuild appendices | `--check`: current |
| Release | Only the actual new `history/2.3.1/` was frozen; all SHA-256 sums verify |

The original 68 guard/test pairings are retained. Five additional mutants cover direct junk paths, protected index paths, a partly moved v1 directory, interrupted relocation settlement, and compaction after a failed sync with durable changes. Each runnable kill was inspected for the guard's own failure. Unavailable historical fixtures are an explicit A6 skip; other skips count as surviving mutants.

The runnable agent scenarios were e1, e2, e6–e8, e10–e12, and e14–e16. Each fresh agent received the recorded user request, sandbox prompt, and installed skill; it saved its own answer. The scorer used disk state, command logs, and those answers. Scorer verification does not add new entries to the agent command log. Setup archives for the 2.3 scenarios were written by this actual rebuild, so their writer is 2.3.1 rather than an invented 2.3.0.

[Machine-readable results](rebuild-validation.json), [pytest report](rebuild-evidence/pytest.xml), [mutation results](rebuild-evidence/mutation-results.json), [scorer self-test](rebuild-evidence/scorer-selftest.json), and [agent answers and command logs](rebuild-evidence/agents/) preserve the evidence. Some raw agent logs also include read-only scorer verifies from earlier scoring passes.

## Recovery limits

The recording's 3,019 editor line positions were transcribed into `archive-icloud-guide.md`, with the separate Downloads copy identical. The recovered guide was preserved unchanged while the implementation and supplemental appendices were built.

Byte identity with the original Markdown cannot be certified. The recovered upgrade appendix matches footer checksum `bc75943216a6`, and the Swift appendix matches `edc0305cd2cb`. The main skill appendix hashes to `5628bad8945b…`, while the footer says `bb506761548a`. That mismatch remains unresolved; invisible whitespace and possible source/appendix drift cannot be distinguished from the recording alone. See [recovery.json](recovery.json) for the full hashes.

The original releases 1.0.0, 2.0.0, 2.1.0, 2.2.0, 2.2.1, and 2.3.0 were unavailable. No stand-in releases were created. Consequently, 104 tests, 21 mutants, scenarios e3/e4/e5/e9/e13, and the historical probes are skipped. Built-in legacy readers and upgrade steps were additionally exercised using literal published-format fixtures; those are not proof of compatibility with the missing original executables. Historical `--via-history` reads require the authentic release files; the rebuild's own frozen release is available.

The prior migration snapshots/logs and historical evaluation records were not present in the recording. Their old filenames and hashes remain in the recovered guide; no replacement run records were fabricated. The architecture HTML/JSON views are new explanatory views of the rebuild.

The generic skill-creator linter rejects the recovered frontmatter keys `version` and `argument-hint`. The main description is also 1,205 characters, beyond that linter's 1,024-character limit. These fields and wording were retained to follow the guide's verbatim-copy requirement. YAML parsing and shared source resolution pass; this is an outstanding generic lint exception.

All archive, restore, import, and upgrade checks used disposable local archive roots. No real project was archived or migrated, and no real iCloud upload/eviction test was performed.

## Reproduce

From the skill folder:

```sh
uv run --with pytest --with pytest-timeout python -m pytest -q --timeout=90 claude/test_*.py
uv run --with pytest --with pytest-timeout python claude/_mutate.py
python3 claude/_selftest_evals.py
uv run --with pytest --with pytest-timeout python claude/_guide_appendices.py --check
python3 claude/_release.py --check
swiftc -typecheck icloud_status.swift
```

Use `_setup_evals.py <new-directory>` for fresh agent sandboxes and `_score_evals.py <directory>` to score their saved answers. Existing sandboxes are never overwritten. `_park_inventory.py snap` and `diff` support a future explicitly authorized migration of real data.
