# Stable agent-manager shell entrypoint. Claude-specific account and mode helpers remain in
# claude.zsh; additional agent adapters can add their own shell modules here later.
_AGENT_MANAGER_ENTRY="${${(%):-%N}:a}"
source "${_AGENT_MANAGER_ENTRY:h}/claude.zsh"
unset _AGENT_MANAGER_ENTRY
