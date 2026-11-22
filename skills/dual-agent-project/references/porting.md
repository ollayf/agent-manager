# Conversion decisions

## One home for shared content

| Concern | Shared source and adapter |
|---|---|
| Project instructions | Keep existing `AGENTS.md` or `CLAUDE.md`; relative-link the other. Resolve conflicting instructions before linking. |
| Project skills | Link the entire `.agents/skills` and `.claude/skills` directories, preserving the existing physical root and relative references. |
| Global skills | Agent-manager `skills/`, linked from both agents and all Claude profiles. Create globally by default. |
| MCP | Shared `.mcp.json`; render Codex's `[mcp_servers]` into a managed config block. Keep existing non-MCP settings. |
| Permission denies | Preserve shared `.claude/settings.json`; generate matching Codex `disabled_tools` and forbidden shell prefixes. |
| Scripts, templates, reference data | Same project paths used by both agents. No agent-specific duplicate directory. |
| Model choice, UI, trust, sessions, secrets | Agent-native or machine-local; retain separately. |

Two linked paths are entrypoints to one file, not two synchronized copies. Git stores a
symlink and the physical source independently. Keep links relative and test clone support.

## Boundaries that require judgment

- Claude `@file` imports are not Codex imports. Share the needed instructions explicitly,
  including nested directory scopes. A Markdown link alone is not automatic inheritance.
- Shared skills can contain references and scripts. Preserve their relative paths and explicit
  handoffs; opening a `SKILL.md` is the fallback when an agent has no native invocation tool.
- Claude plugins, marketplace identities, hooks, commands and custom subagents use native
  schemas. Do not copy `.claude/settings.json` into TOML or assume a matching feature exists.
  Put reusable behavior in shared skills/scripts and wire supported native adapters using
  current docs. Preserve original behavior until a replacement has been verified.
- Codex `.rules` encode more than denies. Translate each forbidden prefix into the shared
  deny policy where expressible, retain existing native rule files, and review any allow/prompt
  rules independently. Never turn an approval into an unconditional allow.
- Connector aliases may have no transport in the other app. Preserve the behavioral restriction
  in shared instructions; never invent a commandless MCP server to attach a deny list.
- Shell prefix rules are not a general ban on arbitrary programs or scripts. Preserve the
  user's policy even when it cannot be enforced identically by each native runtime.
- Claude `${VAR}` interpolation in MCP fields does not become Codex interpolation by copying
  the literal. Use an appropriate shared env-loading launcher or explicit native adapter.
  Keep literal credentials out of tracked sources and generated files. The importer refuses
  credential-looking env/header fields; still inspect commands/args without printing values.
- HTTP/SSE transports, header helpers, OAuth, tool allowlists, per-tool approvals and native
  startup settings need explicit mapping if outside the adapter's supported subset. Preserve
  them in the original native config until conversion is complete; never silently omit them.
- `MCP_TOOL_TIMEOUT` in the shared server environment is an existing convention consumed by
  the adapter to set Codex `tool_timeout_sec`. A newly imported Codex-only timeout does not
  automatically configure Claude's client timeout; verify and wire that separately.
- OAuth tokens and desktop/web connector sessions do not move with shared config. Project
  trust and permissions must be set up in each app. Do not grant trust on the user's behalf.
- Native per-agent tool names can change (`palmier-pro` vs `palmier_pro`, for example).
  Describe the capability and resolve the current tool schema; don't bulk-rename text that
  contains the provider's canonical IDs or historical evidence.

## Verification references

Confirm installed behavior before relying on format assumptions:

- [Codex skills and discovery](https://learn.chatgpt.com/docs/build-skills)
- [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
- [Codex configuration](https://learn.chatgpt.com/docs/config-file/config-reference)
- [Codex rules](https://learn.chatgpt.com/docs/agent-configuration/rules)
- [Claude Code memory](https://code.claude.com/docs/en/memory)
- [Claude Code skills](https://code.claude.com/docs/en/skills)
- [Claude Code MCP](https://code.claude.com/docs/en/mcp)

Use `codex mcp list` to check parsed config and `codex execpolicy check --rules <file> -- <command>`
for representative rules. These do not prove live authentication. List tools or perform a
read-only call through the actual session or an MCP client to verify a connection.
