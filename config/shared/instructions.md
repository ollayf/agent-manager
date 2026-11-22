# User Preferences

## Git

Never run `git commit` or `git push`. Committing and pushing are mine.

Never run anything that destroys history: `git init` in an existing repo, `reset --hard`,
`rebase`, `checkout --orphan`, or deleting `.git`.

Reading (`status`, `diff`, `log`, `show`) and staging (`git add`) are fine. When a change is
ready, stop and print the exact commands for me to run.

## Skills

User-global skills are shared by Claude Code and Codex. Create them through `agent-skills
create <name> --scope global`, or write through the agent's global skills directory. Use
`--scope project` only when the skill is intentionally limited to the current repository.

## Shared projects

Keep Claude Code and Codex project instructions and skill trees linked to one physical
source. Preserve an existing link direction. New skills, references, templates and workflow
data must be available to both agents through that shared source.

Use `dual-agent-project` when converting a project or repairing compatibility drift. Native
MCP/settings files are adapters: edit their shared sources and regenerate them together.
Check new hooks, commands, subagents and plugins for both agents; do not assume copying a
native configuration makes its behavior portable. Credentials and login sessions stay local.

## Archive General
- `archive-general` is the one shared skill for setup, archive/sync, read, restore, verify/recovery, import and upgrade across registered SSD/local, iCloud and Google Drive filesystem targets.
- Preserve the agreed archive structure on every archive: keep the recorded target and project root, mirror repo-relative paths under `files/`, use `.big/` and `.versions/` for their established purposes, and park only eligible folder structure under `_archive/<same path>` (or its recorded park name). Retain legacy layouts until an authorized planned upgrade. Do not invent, flatten, rename or relocate the structure; ask the user before acting when any destination or layout choice is unclear.
- A missing project file may be archived. Check its owning project's `ARCHIVE.md` / `ARCHIVE.manifest.jsonl`, older `ICLOUD.md` / `ICLOUD.manifest.jsonl`, the registry and any older cleanup manifest before saying it is gone.
- Use `python3 ~/.claude/skills/archive-general/archive.py --repo <project root> read <absolute path>` to locate archived content. A printed raw path is read in place. For compressed samples use `read --head N`; a full read above 10,000,000,000 original bytes requires `--full` and free space.
- Restore only when requested. Never edit archive maps, registry files, archive data or parked folder structure by hand. `_archive/<path>` is parked folder structure; its prefix maps to the same archived project path.
- The machine-local target configuration and archive identity marker bind a project to its drive. Check `target list` / `target doctor`. An offline drive or wrong marker/volume UUID is a refusal, not a missing-data repair opportunity. Changing the default affects new projects only and does not migrate old archives.
- Local/SSD copies need no cloud upload or eviction. Native iCloud uses upload-status then eviction after upload. Google Drive mounted-folder copies have no automatic remote-upload confirmation or eviction: report remote status as unknown and never infer cloud durability from local-copy success.
- Direct Google Drive API targets are a separate mode: resumable uploads and verified cloud size/SHA-256 plus durable local/cloud records precede local removal. Use the registered account/folder/marker identity and the agreed folder hierarchy. Existing mounted-folder and SSD archives never migrate implicitly; ask before choosing a permanent Drive destination.
- For imports or upgrades, read the corresponding reference inside the same Archive General skill, show the plan, and check authorization. Explicit approval already given for the same scope remains valid; do not ask repeatedly.

## Versioned Skill Artifacts
- A skill that writes lasting artifacts (archives, datasets, indexes) stamps each one with the skill version that wrote it, and a format number when the on-disk layout matters.
- The newest version reads every past format by default (e.g. still decompresses what an old version compressed). It also keeps each release's own code and SKILL.md, frozen with SHA256SUMS in `history/<version>/`. When the built-in reader fails, it falls back to the code of the version that wrote the artifact.
- Changes to the layout get a new format number and an upgrade step (old → new, resumable, plan first). Never edit a released `history/` folder.
