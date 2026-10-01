# Codex adapter. Sourced by install.sh and doctor.sh.

codex_adapter_available() { command -v codex >/dev/null 2>&1; }

codex_adapter_install_root() {
  ensure_dir "$(dirname "$AGENTS_DIR")"
  link_managed "$MANAGER_CURRENT/skills" "$AGENTS_DIR" "skills/codex-universal"
}

codex_adapter_install_instructions() {
  ensure_dir "$CODEX_DIR"
  link_managed "$MANAGER_CURRENT/config/shared/instructions.md" "$CODEX_DIR/AGENTS.md" "instructions/codex-AGENTS.md"
}

codex_adapter_install_settings() {
  local defaults="$REPO/config/codex/defaults.toml"
  local current="$CODEX_DIR/config.toml"
  local tmp
  ensure_dir "$CODEX_DIR"
  tmp="$(mktemp)"
  python3 "$REPO/lib/codex_config.py" "$defaults" "$current" "$tmp" || { rm -f "$tmp"; fail "Codex settings merge failed"; return 1; }
  if [ -f "$current" ] && cmp -s "$tmp" "$current"; then
    rm -f "$tmp"
    info "$(shortp "$current") portable defaults already current"
  elif [ "$DRY_RUN" = 1 ]; then
    run "merge portable defaults into $(shortp "$current")"
    rm -f "$tmp"
  else
    [ -e "$current" ] && stash "$current" "codex/config.toml"
    mv "$tmp" "$current"
    chmod 600 "$current"
    ok "$(shortp "$current") portable defaults merged"
  fi
}

codex_adapter_sync_plugins() {
  local manifest="$REPO/config/codex/plugins.json"
  codex_adapter_available || { warn "Codex CLI missing — plugin baseline deferred"; return 0; }
  [ -f "$manifest" ] || return 0
  local live selector
  if ! live="$(python3 - <<'PY'
import subprocess, sys
try:
    result = subprocess.run(
        ["codex", "plugin", "list", "--json"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
except (OSError, subprocess.TimeoutExpired):
    raise SystemExit(1)
if result.returncode:
    raise SystemExit(result.returncode)
sys.stdout.write(result.stdout)
PY
)"; then
    warn "Codex plugin inventory unavailable after 10s — plugin baseline deferred"
    return 0
  fi
  printf '%s' "$live" | jq -e . >/dev/null 2>&1 || { warn "Codex plugin inventory was not valid JSON — plugin baseline deferred"; return 0; }
  while read -r selector; do
    [ -n "$selector" ] || continue
    if printf '%s' "$live" | jq -e --arg s "$selector" '
         any(.installed[]?; (.pluginId // ((.name // "") + "@" + (.marketplaceName // ""))) == $s)
       ' >/dev/null 2>&1; then
      info "$selector: installed"
    elif [ "$DRY_RUN" = 1 ]; then
      run "codex plugin add $selector"
    else
      codex plugin add "$selector" >/dev/null && ok "$selector installed" || warn "$selector could not be installed"
    fi
  done < <(jq -r '.plugins[] | "\(.name)@\(.marketplace)"' "$manifest")
}

codex_adapter_doctor() {
  if [ -L "$AGENTS_DIR" ] && [ "$(readlink "$AGENTS_DIR")" = "$MANAGER_CURRENT/skills" ] && [ -d "$AGENTS_DIR/" ]; then
    ok "$(shortp "$AGENTS_DIR") -> shared registry"
  else
    fail "$(shortp "$AGENTS_DIR") is not linked to the shared registry"
    return 1
  fi
  [ -e "$CODEX_DIR/AGENTS.md" ] || { fail "$(shortp "$CODEX_DIR/AGENTS.md") missing"; return 1; }
  ok "Codex instructions installed"
}
