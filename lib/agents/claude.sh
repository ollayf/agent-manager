# Claude Code adapter. Sourced by install.sh and doctor.sh.

claude_adapter_available() { command -v claude >/dev/null 2>&1; }

claude_adapter_install_roots() {
  local root label
  while read -r root; do
    [ -n "$root" ] || continue
    ensure_dir "$(dirname "$root")"
    if [ "$root" = "$CLAUDE_DIR/skills" ]; then
      label="skills/claude-primary"
    else
      label="skills/claude-$(basename "$(dirname "$root")")"
    fi
    link_managed "$MANAGER_CURRENT/skills" "$root" "$label"
  done < <(claude_skill_roots)
}

claude_adapter_install_instructions() {
  local dst
  link_managed "$MANAGER_CURRENT/config/shared/instructions.md" "$CLAUDE_DIR/CLAUDE.md" "instructions/primary-CLAUDE.md"
  local profile
  while read -r profile; do
    [ -n "$profile" ] || continue
    dst="$CLAUDE_PROFILES_HOME/$profile/CLAUDE.md"
    ensure_dir "$(dirname "$dst")"
    link_managed "$MANAGER_CURRENT/config/shared/instructions.md" "$dst" "instructions/$profile-CLAUDE.md"
  done < <(profile_names)
}

claude_adapter_doctor() {
  local root bad=0
  while read -r root; do
    [ -n "$root" ] || continue
    if [ -L "$root" ] && [ "$(readlink "$root")" = "$MANAGER_CURRENT/skills" ] && [ -d "$root/" ]; then
      ok "$(shortp "$root") -> shared registry"
    else
      fail "$(shortp "$root") is not linked to the shared registry"
      bad=$((bad+1))
    fi
  done < <(claude_skill_roots)
  return "$bad"
}
