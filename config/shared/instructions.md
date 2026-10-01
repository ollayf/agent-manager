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
