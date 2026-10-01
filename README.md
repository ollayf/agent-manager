# agent-manager

One repository for skills and portable settings shared by Claude Code, every Claude account,
and Codex. Agent-native authentication, sessions and runtime state stay local.

## Bootstrap a machine

```bash
git clone <remote> ~/develop/agent-manager
cd ~/develop/agent-manager
cp secrets.env.example secrets.env   # optional Claude provider modes
$EDITOR secrets.env
./install.sh
./doctor.sh
```

The checkout can live anywhere. The installer records one active checkout per machine under
`~/.config/agent-manager/` and exposes it through
`~/.local/share/agent-manager/current`. A second clone cannot silently take over:

```bash
agent-manager root status
agent-manager root switch /path/to/other/clone
```

Root switching refuses while the old checkout has uncommitted changes.

## The central invariant

`skills/` is the single physical user-global skill tree:

```text
~/.claude/skills --------------------┐
~/.claude-profiles/claude2/skills ---┤
~/.claude-profiles/claude3/skills ---┼──> agent-manager/skills/
~/.agents/skills --------------------┘
```

Creating or editing a skill through any global path changes the same files. Codex's
`~/.codex/skills` is not managed; Codex uses it for system and plugin skills.

Tracked directories in `skills/` are yours. Names in `vendor.json` are ignored recipes that
can be rebuilt from upstream or `mirror/`. `skills/.gitignore` is generated from the manifest.

## Creating skills

```bash
agent-skills create my-skill --scope global
agent-skills create repo-checks --scope project --project /path/to/project
```

Global is the default and reaches every Claude account plus Codex. Project scope creates the
canonical skill under `<project>/.agents/skills`; the entire `<project>/.claude/skills` directory
is a relative link to that tree. Direct skill writes by either agent therefore reach the same
physical files.

A skill written directly through an agent's linked global directory still lands in this repo.
Doctor treats an unknown name as repo-owned, validates its metadata, and reports collisions.

## Claude accounts

`claude`, `claude2`, `claude3`, and future profiles retain separate logins and settings overlays.
They share the skill registry and global instructions. Existing Claude behavior remains:

- plugin enablement and marketplaces inherit from primary Claude;
- user MCP definitions mirror from primary Claude;
- MCP OAuth tokens reconcile across Claude Keychain slots;
- the current sessions/history sharing policy is unchanged.

```bash
claude-account list
claude-account add claude4
claude-account remove claude4
```

## Settings and MCP

- `config/shared/instructions.md` feeds Claude's `CLAUDE.md` and Codex's `AGENTS.md`.
- `config/codex/defaults.toml` owns a marked block in Codex config while preserving trust,
  projects, plugins and other machine-local content.
- `config/shared/mcp.json` records secret-free MCP intent. Environment mappings contain variable
  names, never token values. `agent-mcp sync` adds missing servers to both agents.
- Claude and Codex plugins use separate manifests and native CLIs.

## Commands

| Command | Purpose |
|---|---|
| `agent-manager install` / `./install.sh` | idempotent bootstrap or reconciliation |
| `agent-manager pull` | gather live shared state for review |
| `agent-manager push` | run safety checks and print Git commands |
| `agent-manager doctor` / `./doctor.sh` | verify local installation |
| `./doctor.sh --portable` | additionally require a commit and remote |
| `agent-manager root status\|switch` | inspect or change the active checkout |
| `agent-manager project init [path]` | add shared project instructions and skill roots |
| `agent-skills create` | create a global or project skill safely |
| `agent-skills sync --offline` | restore vendor skills from the committed mirror |
| `agent-skills update\|adopt\|mirror\|status` | maintain skill ownership and recipes |
| `agent-mcp sync\|status` | reconcile portable MCP definitions |

The old `claude-manager` and `claude-skills` names remain compatibility entrypoints.

## Safety

- Replaced paths move to timestamped backups under `~/.local/share/agent-manager/backups/`.
- `--dry-run` prints actions without applying them; `--check` reports drift.
- Authentication, OAuth tokens, histories, caches, trusted-project records and rendered secrets
  are never committed.
- No manager command runs `git commit` or `git push`.
- On a fresh clone, owned skills arrive through Git; vendor recipes restore from upstream or the
  offline mirror. Claude and Codex logins are completed separately on that machine.
