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

# ---------------------------------------------------------------- model modes
#
# Swap the primary account between Anthropic and GLM/BytePlus backends. Ported verbatim
# from the pre-repo .zshrc. The mode-config files are rendered from templates by
# install.sh and hold live tokens, so they stay outside the repo.

_claude_current_profile() {
  local state=~/.claude/.current_profile
  [[ -f "$state" ]] && cat "$state" || echo "unknown"
}

_apply_claude_mode() {
  local mode=$1
  local config=~/.claude/mode-configs/${mode}.json
  local other_mode
  [[ "$mode" == "claude" ]] && other_mode="glm" || other_mode="claude"
  local other_config=~/.claude/mode-configs/${other_mode}.json

  if [[ ! -f "$config" ]]; then
    echo "❌ Mode config not found: $config" >&2
    echo "   Run: $CLAUDE_HELPERS/install.sh   (renders it from the template + secrets.env)" >&2
    return 1
  fi

  # Smart merge: drop the other mode's plugins, add this mode's, preserve user-installed extras.
  local merge_jq='
    .env = $m.env
    | .enabledPlugins = (
        (.enabledPlugins // {})
        | with_entries(select(.key as $k | ($other.enabledPlugins | has($k)) | not))
        | . + $m.enabledPlugins
      )
    | .extraKnownMarketplaces = (
        (.extraKnownMarketplaces // {})
        | with_entries(select(.key as $k | ($other.extraKnownMarketplaces | has($k)) | not))
        | . + $m.extraKnownMarketplaces
      )
  '

  local tmp=$(mktemp)
  jq --argjson m "$(cat "$config")" --argjson other "$(cat "$other_config")" \
    "$merge_jq" ~/.claude/settings.json > "$tmp" && mv "$tmp" ~/.claude/settings.json

  # Profile parity is automatic: claude-profile mirrors primary's enabledPlugins and
  # extraKnownMarketplaces on every launch. Syncing here too would be a competing system.

  echo "$mode" > ~/.claude/.current_profile
}

use-glm()    { _apply_claude_mode glm    && echo "✅ Switched to GLM"; }
use-claude() { _apply_claude_mode claude && echo "✅ Switched to Claude"; }

# ---------------------------------------------------------------- convenience

# Jump to the repo; with an argument, straight into that skill.
cskills() {
  if [[ -n "${1:-}" ]]; then cd "$CLAUDE_HELPERS/skills/$1"; else cd "$CLAUDE_HELPERS"; fi
}
