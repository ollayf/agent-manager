# Moving conversations and memory to another machine

`agent-state` copies your Claude Code and Codex conversations and memory into one bundle folder,
grouped by project. On the new machine it puts each file back where the agents look for it.

```text
old machine                                   new machine
~/.claude/projects/…  ─┐                   ┌─▶ ~/.claude/projects/…
~/.codex/sessions/…   ─┼─▶ bundle ─▶ .dmg ─┼─▶ ~/.codex/sessions/…
project CLAUDE.local.md┘   (scan,  (encrypt)└─▶ <project>/CLAUDE.local.md
                           redact)
```

## What the bundle holds

```text
agent-state-YYYYMMDD-HHMMSS/
  README.md              this file
  MANIFEST.json          every file with its SHA-256, plus the project list
  SECRETS-REPORT.txt     file:line and detector for every token found (never the value)
  projects/
    develop__video-gen__openfield/      one folder per project, named after its path under ~
      project.json       original path, counts, git status at export time
      claude/sessions/   Claude transcripts (<id>.jsonl) and their subagents/tool results
      claude/memory/     Claude's auto memory for that project (MEMORY.md and topic files)
      codex/sessions/    Codex rollouts for that project, in Codex's date folders
      files/             CLAUDE.local.md, and CLAUDE.md/AGENTS.md if git won't carry them
    _home/                sessions started in ~ itself
    _root__Volumes__…/    projects outside your home folder
    _unresolved__…/       folders that no longer exist; kept by their Claude name
  global/
    claude/main/         prompt history (history.jsonl), paste cache, file checkpoints, tasks
    claude/claude2/      per-profile plans and paste cache
    codex/               prompt history, thread names, Codex memories
```

**Not included:** logins and OAuth tokens, `settings.json`, `~/.claude.json` (trust and account
records), `~/.codex/config.toml` and `auth.json`, and the agents' caches and SQLite indexes.
These belong to one machine. The repo and `secrets.env` recreate the settings, and you log in
again.

## On the old machine

```bash
agent-state export --dry-run          # list projects, sizes and secret findings; writes nothing
agent-state export                    # writes ~/agent-state-exports/agent-state-<time>/
agent-state pack ~/agent-state-exports/agent-state-<time>    # encrypted .dmg, asks for a password
```

- Read `SECRETS-REPORT.txt`. Redacted tokens are replaced with `[REDACTED:<detector>]` in the
  copy. Lines marked `REVIEW` could not be redacted safely. Rotate those credentials, or delete
  that session from the bundle before packing.
- The summary flags projects with `no remote`, `unpushed/dirty` or `not a git repo`. Their own
  code does not travel in this bundle, so push them first.
- `--project PATH` (repeatable) exports only those projects and skips global history.
- The bundle holds private conversations. Move it only as the encrypted `.dmg`, using AirDrop,
  a USB drive or a private cloud folder. Never put it in git.

## On the new machine

```bash
# 1. set up the repo first (README "Bootstrap a machine"), log in to claude / codex
# 2. open the .dmg (double-click, enter the password)
agent-state verify  /Volumes/agent-state-<time>/agent-state-<time>
agent-state import  /Volumes/agent-state-<time>/agent-state-<time>            # preview
agent-state import  /Volumes/agent-state-<time>/agent-state-<time> --apply    # write
```

- **Different username or folder layout.** Your old home folder is mapped to the new one
  automatically. For anything else, add `--map OLD=NEW`, for example
  `--map /Volumes/Work/code=$HOME/code`. Every recorded value that is itself a path moves:
  working folders, Codex workspace roots and sandbox paths, file paths in tool calls. Text that
  only mentions a path, such as a command you ran, stays exactly as it was.
- **Nothing is overwritten.** A file that already exists and differs is kept and listed. The
  prompt histories are merged by time; the previous file is first copied to
  `~/.local/share/agent-manager/backups/state-import-<time>/`. Re-running is safe.
- **Codex.** If Codex has already been opened on this machine, it will not list sessions copied
  in afterwards. Quit Codex and run `agent-state import <bundle> --apply --reindex-codex`. That
  moves Codex's index into the backup folder, and Codex rebuilds it from the sessions on its next
  start.
- **Waiting items.** `files/` go into a project only once that project is cloned at its new
  path. Profile plans need the profile first (`claude-account add claude2`). Run the import
  again after either step.
- Quit Claude and Codex during `--apply`, so neither writes to its history file at the same time.

## Check it worked

```bash
cd ~/develop/<project> && claude --resume     # earlier sessions are listed
codex resume --all                            # Codex sessions, all folders
```

Once the import checks out, delete the plain bundle folder and keep only the encrypted `.dmg`,
or delete that too.
