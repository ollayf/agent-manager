#!/usr/bin/env bash
#
# install.sh — wire this repo into Claude Code, Codex, ~/.local/bin and the shell.
# run it as often as you like, on this machine or a fresh one.
#
#   ./install.sh              perform the work
#   ./install.sh --dry-run    print every action, change nothing
#   ./install.sh --check      exit non-zero if anything is out of date (for CI)
#
# Nothing is silently deleted. Everything replaced is moved to the manager backup root.
#
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$REPO/lib/common.sh"

CHECK=0
OFFLINE=0
AGENT_FILTER="auto"
for a in "$@"; do
  case "$a" in
    --dry-run) DRY_RUN=1 ;;
    --check)   DRY_RUN=1; CHECK=1 ;;
    --offline) OFFLINE=1 ;;
    --agents=*) AGENT_FILTER="${a#--agents=}" ;;
    -h|--help) sed -n '3,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown flag: $a" >&2; exit 2 ;;
  esac
done

case "$AGENT_FILTER" in auto|claude|codex|claude,codex|codex,claude) ;; *) echo "invalid --agents value: $AGENT_FILTER" >&2; exit 2 ;; esac

MANAGED_DIRS=(commands agents)

# ---------------------------------------------------------------- preflight

head1 "Preflight"
for t in jq python3 git; do
  command -v "$t" >/dev/null 2>&1 && ok "$t" || { fail "$t is required"; }
done
failures || { say ""; say "Install the missing tools and re-run."; exit 1; }
[ "$DRY_RUN" = 1 ] && info "dry-run: nothing will be modified"

# ---------------------------------------------------------------- active checkout

head1 "Active manager checkout"
active_root="$(manager_active_root)"
if [ -n "$active_root" ] && [ "$(canonical_path "$active_root")" != "$(canonical_path "$REPO")" ]; then
  fail "another checkout is active: $(shortp "$active_root")"
  info "switch explicitly with: $(shortp "$active_root")/bin/agent-manager root switch $(shortp "$REPO")"
  exit 1
fi

ensure_dir "$MANAGER_CONFIG_HOME"
ensure_dir "$MANAGER_DATA_HOME"
link_managed "$REPO" "$MANAGER_CURRENT" "manager-current"
if [ "$DRY_RUN" = 1 ]; then
  [ -f "$MANAGER_STATE" ] || run "write $(shortp "$MANAGER_STATE")"
else
  _state_tmp="$(mktemp)"
  jq -n --arg root "$REPO" '{version: 1, activeRoot: $root}' > "$_state_tmp"
  mv "$_state_tmp" "$MANAGER_STATE"
  ok "active root recorded: $(shortp "$REPO")"
fi

# ---------------------------------------------------------------- shared skill registry

migrate_dir() {
  local name="$1"
  local live="$CLAUDE_DIR/$name" dir="$REPO/$name" linked="$MANAGER_CURRENT/$name"
  local t abs b e
  ensure_dir "$dir"

  if [ -L "$live" ]; then
    t="$(readlink "$live")"
    if [ "$t" = "$linked" ]; then ok "$name -> repo (already linked)"; return 0; fi
    warn "$name points at $(shortp "$t"), not the repo"
    stash "$live" "$name.symlink"

  elif [ -d "$live" ]; then
    info "migrating $(shortp "$live") into the repo"

    # 1. Absolutise relative symlinks WHILE THEY ARE STILL HERE. A relative link resolves
    #    against its physical directory, so moving it silently breaks it. This must happen
    #    before step 2, not after.
    for e in "$live"/*; do
      [ -L "$e" ] || continue
      t="$(readlink "$e")"
      case "$t" in /*) continue ;; esac
      abs="$(link_target_abs "$e")"
      run rm "$e"; run ln -s "$abs" "$e"
      info "absolutised $name/$(basename "$e") -> $(shortp "$abs")"
    done

    # 2. Move every entry across, dotfiles included.
    shopt -s dotglob nullglob
    for e in "$live"/*; do
      b="$(basename "$e")"
      if [ "$b" = ".gitignore" ]; then info "dropping $name/.gitignore (regenerated)"; run rm -f "$e"; continue; fi
      if [ -e "$dir/$b" ] || [ -L "$dir/$b" ]; then
        warn "$name/$b already in repo — keeping the repo copy, backing up the incoming one"
        stash "$e" "$name/$b"
      else
        run mv "$e" "$dir/$b"
      fi
    done
    shopt -u dotglob nullglob

    # 3. Replace the (now empty) directory with the link.
    if [ "$DRY_RUN" != 1 ]; then
      rmdir "$live" 2>/dev/null || stash "$live" "$name.leftover"
    fi
  fi

  run ln -s "$linked" "$live"
  ok "$name -> $(shortp "$linked")"
}

skill_root_conflicts() {
  local live="$1" e name dst
  [ -d "$live" ] && [ ! -L "$live" ] || return 0
  shopt -s dotglob nullglob
  for e in "$live"/*; do
    name="$(basename "$e")"
    case "$name" in .DS_Store|.gitignore) continue ;; esac
    dst="$REPO/skills/$name"
    [ -e "$dst" ] || [ -L "$dst" ] || continue
    if [ -L "$dst" ] && [ "$(canonical_path "$dst")" = "$(canonical_path "$e")" ]; then
      continue
    fi
    if [ -d "$e" ] && [ -d "$dst" ] && diff -qr "$e" "$dst" >/dev/null 2>&1; then
      continue
    fi
    fail "skill conflict '$name': $(shortp "$live/$name") differs from $(shortp "$dst")"
  done
  shopt -u dotglob nullglob
}

skill_live_root_conflicts() {
  local roots=("$AGENTS_DIR") root left right entry name i j
  while read -r root; do [ -n "$root" ] && roots+=("$root"); done < <(claude_skill_roots)
  for ((i=0; i<${#roots[@]}; i++)); do
    left="${roots[$i]}"
    [ -d "$left" ] && [ ! -L "$left" ] || continue
    for ((j=i+1; j<${#roots[@]}; j++)); do
      right="${roots[$j]}"
      [ -d "$right" ] && [ ! -L "$right" ] || continue
      shopt -s dotglob nullglob
      for entry in "$left"/*; do
        name="$(basename "$entry")"
        case "$name" in .DS_Store|.gitignore) continue ;; esac
        [ -e "$right/$name" ] || [ -L "$right/$name" ] || continue
        entries_equal "$entry" "$right/$name" || \
          fail "skill conflict '$name': $(shortp "$entry") differs from $(shortp "$right/$name")"
      done
      shopt -u dotglob nullglob
    done
  done
}

migrate_skill_root() {
  local live="$1" label="$2" e name dst t abs
  [ -d "$live" ] && [ ! -L "$live" ] || return 0
  info "migrating $(shortp "$live") into the shared registry"
  shopt -s dotglob nullglob
  for e in "$live"/*; do
    name="$(basename "$e")"
    dst="$REPO/skills/$name"
    case "$name" in
      .DS_Store|.gitignore) stash "$e" "skills-noise/$label/$name"; continue ;;
    esac
    if [ -L "$e" ]; then
      t="$(readlink "$e")"
      case "$t" in /*) ;; *) abs="$(link_target_abs "$e")"; run rm "$e"; run ln -s "$abs" "$e" ;; esac
    fi
    if [ -L "$dst" ] && [ "$(canonical_path "$dst")" = "$(canonical_path "$e")" ]; then
      stash "$dst" "legacy-skill-links/$name"
      run mv "$e" "$dst"
      ok "$name materialized in the registry"
    elif [ ! -e "$dst" ] && [ ! -L "$dst" ]; then
      run mv "$e" "$dst"
      ok "$name moved into the registry"
    else
      if entries_equal "$e" "$dst"; then
        stash "$e" "duplicate-skills/$label/$name"
        info "$name already exists identically in the registry"
      else
        fail "skill conflict appeared during migration: $(shortp "$e") differs from $(shortp "$dst")"
        return 1
      fi
    fi
  done
  shopt -u dotglob nullglob
  if [ "$DRY_RUN" != 1 ]; then rmdir "$live" 2>/dev/null || stash "$live" "skill-roots/$label.leftover"; fi
}

ensure_dir "$REPO/skills"
skill_root_conflicts "$AGENTS_DIR"
while read -r _root; do skill_root_conflicts "$_root"; done < <(claude_skill_roots)
skill_live_root_conflicts
failures || { say ""; say "Resolve the skill conflicts above before installation."; exit 1; }

head1 "Shared skill registry"
migrate_skill_root "$AGENTS_DIR" "codex-universal"
while read -r _root; do migrate_skill_root "$_root" "claude-$(basename "$(dirname "$_root")")"; done < <(claude_skill_roots)

# shellcheck source=lib/agents/claude.sh
source "$REPO/lib/agents/claude.sh"
# shellcheck source=lib/agents/codex.sh
source "$REPO/lib/agents/codex.sh"

case "$AGENT_FILTER" in
  auto|claude,codex|codex,claude) claude_adapter_install_roots; codex_adapter_install_root ;;
  claude) claude_adapter_install_roots ;;
  codex) codex_adapter_install_root ;;
esac

head1 "Claude-only directories"
for d in "${MANAGED_DIRS[@]}"; do migrate_dir "$d"; done

# ---------------------------------------------------------------- executables

head1 "Executables in $(shortp "$LOCAL_BIN")"
ensure_dir "$LOCAL_BIN"
for f in "$REPO"/bin/*; do
  n="$(basename "$f")"; d="$LOCAL_BIN/$n"; stable="$MANAGER_CURRENT/bin/$n"
  if [ -L "$d" ] && [ "$(readlink "$d")" = "$stable" ]; then ok "$n (already linked)"; continue; fi
  if [ -e "$d" ] || [ -L "$d" ]; then stash "$d" "local-bin/$n"; fi
  run ln -s "$stable" "$d"
  ok "$n -> $(shortp "$stable")"
done

# The claude2/claude3 shims are dead weight now: shell/claude.zsh builds those functions
# from config/profiles.list and calls claude-profile directly.
for n in claude2 claude3; do
  d="$LOCAL_BIN/$n"
  if [ -e "$d" ] || [ -L "$d" ]; then
    stash "$d" "local-bin/$n.obsolete-shim"
    ok "$n shim retired (replaced by profiles.list)"
  fi
done

# ---------------------------------------------------------------- config

head1 "Shared instructions"
link_file() {
  local src="$1" dst="$2"
  if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then ok "$(shortp "$dst") (already linked)"; return 0; fi
  if [ -e "$dst" ] || [ -L "$dst" ]; then stash "$dst" "config/$(basename "$dst")"; fi
  ensure_dir "$(dirname "$dst")"
  run ln -s "$src" "$dst"
  ok "$(shortp "$dst") -> $(shortp "$src")"
}
case "$AGENT_FILTER" in
  auto|claude,codex|codex,claude) claude_adapter_install_instructions; codex_adapter_install_instructions ;;
  claude) claude_adapter_install_instructions ;;
  codex) codex_adapter_install_instructions ;;
esac

head1 "Native settings"
case "$AGENT_FILTER" in auto|codex|claude,codex|codex,claude) codex_adapter_install_settings ;; esac

# ---------------------------------------------------------------- plugins

# Plugins are recipes in config/plugins.json, not vendored code — same bargain as
# vendor.json. `warn`, never `fail`: a machine with no network should still finish the rest
# of the install rather than abort halfway through.
head1 "Plugins"
case "$AGENT_FILTER" in auto|claude|claude,codex|codex,claude) DRY_RUN="$DRY_RUN" "$REPO/bin/claude-plugins" sync || warn "Claude plugin sync reported problems" ;; esac
case "$AGENT_FILTER" in auto|codex|claude,codex|codex,claude) codex_adapter_sync_plugins || warn "Codex plugin sync reported problems" ;; esac

head1 "Skills"
_skill_args=(sync)
[ "$OFFLINE" = 1 ] && _skill_args+=(--offline)
DRY_RUN="$DRY_RUN" "$REPO/bin/agent-skills" "${_skill_args[@]}" || fail "agent-skills sync reported problems"

head1 "MCP servers"
_mcp_args=(sync)
[ "$DRY_RUN" = 1 ] && _mcp_args+=(--dry-run)
"$REPO/bin/agent-mcp" "${_mcp_args[@]}" || warn "MCP sync reported problems"

# ---------------------------------------------------------------- git hook

head1 "Git hook"
if [ -d "$REPO/.git" ]; then
  hk="$REPO/.git/hooks/pre-commit"
  if [ -L "$hk" ] && [ "$(readlink "$hk")" = "../../hooks/pre-commit" ]; then
    ok "pre-commit (already installed)"
  else
    [ -e "$hk" ] && stash "$hk" "git-hooks/pre-commit"
    ensure_dir "$REPO/.git/hooks"
    run ln -s "../../hooks/pre-commit" "$hk"
    ok "pre-commit installed (credential guard)"
  fi
else
  warn "not a git repo yet — run git init, then re-run to install the credential guard"
fi

# ---------------------------------------------------------------- shell

head1 "Shell"
LINE="source $MANAGER_CURRENT/shell/agents.zsh"
if grep -qE "^[[:space:]]*(source|\.)[[:space:]]+.*claude-manager/shell/claude\.zsh" "$HOME/.zshrc" 2>/dev/null; then
  if [ "$DRY_RUN" = 1 ]; then
    run "replace the checkout-specific .zshrc source with '$LINE'"
  else
    _zsh_tmp="$(mktemp)"
    python3 - "$HOME/.zshrc" "$_zsh_tmp" "$LINE" <<'PY'
import re, sys
source, destination, replacement = sys.argv[1:]
pattern = re.compile(r"^\s*(?:source|\.)\s+.*claude-manager/shell/claude\.zsh\s*$")
seen = False
lines = []
with open(source) as handle:
    for line in handle:
        if pattern.match(line):
            if not seen:
                lines.append(replacement + "\n")
                seen = True
        else:
            lines.append(line)
with open(destination, "w") as handle:
    handle.writelines(lines)
PY
    stash "$HOME/.zshrc" "shell/zshrc"
    mv "$_zsh_tmp" "$HOME/.zshrc"
    ok "migrated .zshrc to the stable agent-manager entrypoint"
  fi
elif grep -qF "$LINE" "$HOME/.zshrc" 2>/dev/null; then
  ok ".zshrc sources the stable agent-manager entrypoint"
else
  if [ "$DRY_RUN" = 1 ]; then
    run "append '$LINE' to $(shortp "$HOME/.zshrc")"
  else
    printf '\n%s\n' "$LINE" >> "$HOME/.zshrc"
    ok "installed stable shell entrypoint"
  fi
fi

# ---------------------------------------------------------------- done

head1 "Summary"
if [ -n "$_BACKUP_DIR" ]; then say "  backups: $(shortp "$_BACKUP_DIR")"; fi
if [ "$CHECK" = 1 ]; then
  if pending; then ok "everything up to date"; exit 0
  else say "  ${C_YEL}$_PENDING action(s) pending${C_OFF}"; exit 1; fi
fi
if [ "$DRY_RUN" = 1 ]; then
  say "  $_PENDING action(s) would run. Re-run without --dry-run to apply."
else
    say "  Shared registry ready for Claude accounts and Codex."
fi
failures
