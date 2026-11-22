---
name: dual-agent-project
description: Convert an existing Claude Code-only or Codex-only project to work with both agents, or repair drift in an existing shared setup. Use for requests to share project instructions, skills, MCP servers and workflow tooling between Claude Code and Codex. Includes the agent-manager global skill conventions. Does not migrate account logins or assume Claude cloud/desktop connectors exist in Codex.
---

# Share a project between Claude Code and Codex

Owns conversion and verification of a project's agent setup. Does not own its product code,
account authentication, or automatic translation of agent-specific execution features.
Preserve the user's current work and project conventions. A conversion request authorizes
local edits and checks; finish those without asking for routine confirmation.

The intended result is one physical copy of each shared instruction, skill, script and data
file. Native settings are adapters around those shared sources. Copying two skill trees and
hoping to keep them synchronized does not meet the request.

## Inspect first

1. Resolve the project path; read its instructions and Git status. Keep existing edits.
   Inspect root and nested `AGENTS.md` / `CLAUDE.md`, skill roots, `.mcp.json`,
   `.claude/settings*.json`, `.codex/config.toml`, `.codex/rules/`, commands, hooks,
   custom agents and referenced scripts. Inventory names and fields without printing secrets.
2. Read [the porting guide](references/porting.md). Verify current config syntax through the
   installed CLIs and official docs; when available, invoke `openai-docs` for Codex specifics.
   File sharing is stable; native settings and available tools change.
3. Locate `agent-manager` using `command -v` and `agent-manager root status`.
   Do not hard-code `~/claude-manager`: the installed checkout may live elsewhere.
   Use its README and shared config to preserve this machine's ownership conventions.
   Global skills should resolve to its `skills/` through both `~/.claude/skills`
   and `~/.agents/skills`, including other Claude profiles. Leave `~/.codex/skills` alone.

## Share the files

Run `agent-manager project init <project> --dry-run`, inspect the result, then run without
`--dry-run`. No separate approval is needed for this requested, reversible conversion.
The manager preserves an existing shared link direction and links an existing single root.
If unavailable, perform the same actions locally: use relative symlinks, preserve existing
physical roots, and archive paths before replacing them.

If both instruction files or same-named skills differ, read and reconcile them first.
Merge compatible guidance into one source, keep a backup outside discovery, and link the
other entrypoint to it. Ask only about an actual contradictory user choice that evidence
cannot resolve. Never make an empty `AGENTS.md` that loses existing Claude guidance.
Handle nested instruction scopes too; resolve Claude `@imports` into explicit shared
guidance/links where Codex would otherwise miss instructions. Move evaluation snapshots
outside every discoverable skill root, preserving their contents.

Once shared, add project-specific creation guidance to the shared project instructions:

- New global skills: `agent-skills create <name> --scope global`.
- Intentionally project-local skills: `agent-skills create <name> --scope project --project <path>`.
- Preserve the directory symlink, so future skills, references and assets appear to both agents.
- Edit shared files at their physical source if an editor would replace a symlink.
- Keep reusable instructions and workflow data shared; explicitly adapt each native-only feature.

## MCP and permissions

Use `.mcp.json` as the shared project MCP source and `.claude/settings.json` as the shared
deny source when adopting the bundled adapter. Preserve an existing source/adapter system
that already works; extend it instead of installing a competing one.

For a Codex-only project with MCP definitions, run the bundled importer with Python 3.11+
(or Python with `tomli`), first in its default preview mode:

```bash
python3 <skill-dir>/scripts/import_codex.py <project>
python3 <skill-dir>/scripts/import_codex.py <project> --apply
```

It validates against the bundled adapter before writing, preserves all non-MCP native
settings, merges matching shared definitions, and backs up existing files outside the repo.
Unknown transport/settings, credential literals, or conflicting sources stop the import.
Handle those with an explicit, reviewed adapter; do not delete fields to get a green check.
Native `.rules` policies still need separate review and translation into the shared policy.

When no shared MCP/deny files exist, create the minimal empty source objects. Install
[assets/sync_agent_config.py](assets/sync_agent_config.py) as the project's
`scripts/sync_agent_config.py` and [assets/codex](assets/codex) as `scripts/codex` only when
those paths are free, or reconcile their existing implementations. Make the launcher
executable. The adapter supports either link direction, stdio/HTTP, matching MCP tool denies,
shell prefix denies and the timeout convention already present in the MCP environment.
It preserves unrelated Codex settings outside its managed block and fails on unsupported
shared settings. See the guide for limitations and for native-only features needing judgment.

Run from the project root:

```bash
python3 scripts/sync_agent_config.py
python3 scripts/sync_agent_config.py --check
```

Document sources and refresh commands in the project README; require regeneration in the
same change as MCP/deny edits. Add `--check` to the project's existing setup/check entrypoint
or CI. The launcher refreshes before Codex starts; app/IDE sessions need a refresh and restart
after settings changes. Keep account credentials, trust records and runtime state local.

## Port workflows and verify

Read each active skill and follow its references. Translate instructions such as `ToolSearch`,
`Read` for images, and `Skill` invocation into capability-based language or a shared mapping.
Use exposed tool schemas, not guessed MCP identifiers. Preserve paid/approval gates.
Search scripts for CLI/subprocess dependencies; distinguish a deliberately fixed model
backend from an accidental dependency on the launching agent. Do not change a calibrated
judge/model just to remove the word `claude`; state its remaining dependency.

Verify actual outcomes:

- Instruction and skill paths resolve to the same files. Edits and new skill directories
  through either entrypoint reach the other. Use isolated fixtures for creation/edit tests.
- Native configs parse in the installed clients; rendered MCP names, launch commands, env,
  timeouts and denies agree. Test the generated rules against representative denied commands.
- Run `python3 -m unittest discover -s <skill-dir>/tests -v` with Python 3.11+
  (or Python with `tomli`), and the project's required checks.
- Initialize/list tools or use an inexpensive read on each available MCP. Configuration
  listing alone is not a successful connection. Never generate paid media for a setup check.
- Check local script parsing and links; run meaningful smoke tests for changed workflows.
  A syntax check does not verify an entire media pipeline.

Report what is shared, what changed, checks performed and concrete remaining dependencies.
Do not claim universal feature parity for untranslated hooks, native subagents or connectors.
Finish with exact Git staging/commit commands for the user; never commit, push, discard
working changes, or delete generated media. For symlinked skill edits, stage the physical source.
