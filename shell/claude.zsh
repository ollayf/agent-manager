# claude-manager shell integration.
#
# Add exactly one line to ~/.zshrc:
#     source ~/.local/share/agent-manager/current/shell/agents.zsh
#
# Everything below is derived from config/profiles.list, so adding a fourth account is
# one word in that file plus a new shell — no new script, no new function, no .zshrc edit.

_AGENT_MANAGER_SHELL_FILE="${${(%):-%N}:a}"
CLAUDE_HELPERS="${CLAUDE_HELPERS:-${_AGENT_MANAGER_SHELL_FILE:h:h}}"
unset _AGENT_MANAGER_SHELL_FILE

# Local, gitignored: API tokens that must never reach the repo.
[[ -f "$CLAUDE_HELPERS/secrets.env" ]] && source "$CLAUDE_HELPERS/secrets.env"

# ---------------------------------------------------------------- accounts

# Primary account (~/.claude). claude-mcp-sync shares MCP OAuth tokens across every
# account's Keychain slot, so a /mcp reconnect done anywhere is picked up here too.
claude()  { command claude-mcp-sync || true; command claude "$@"; }
clauded() { claude --dangerously-skip-permissions "$@"; }

# Any named profile: its own login and config dir, everything else inherited from primary.
# claude-profile runs claude-mcp-sync itself.
claudep() {
  local p="${1:?usage: claudep <profile> [claude args...]}"; shift
  command claude-profile "$p" --dangerously-skip-permissions "$@"
}

# One function per line of config/profiles.list.
if [[ -r "$CLAUDE_HELPERS/config/profiles.list" ]]; then
  for _p in ${(f)"$(<$CLAUDE_HELPERS/config/profiles.list)"}; do
    [[ -z "$_p" || "$_p" == \#* ]] && continue
    eval "${_p}() { claudep ${_p} \"\$@\"; }"
  done
  unset _p
fi

# ---------------------------------------------------------------- convenience

# Jump to the repo; with an argument, straight into that skill.
cskills() {
  if [[ -n "${1:-}" ]]; then cd "$CLAUDE_HELPERS/skills/$1"; else cd "$CLAUDE_HELPERS"; fi
}
