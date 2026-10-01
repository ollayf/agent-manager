# Shared helpers for the agent-manager commands.
# Sourced, never executed. Assumes `set -euo pipefail` in the caller.

: "${REPO:?REPO must be set before sourcing common.sh}"

CLAUDE_DIR="${CLAUDE_PRIMARY_CONFIG_DIR:-$HOME/.claude}"
CODEX_DIR="${CODEX_HOME:-$HOME/.codex}"
AGENTS_HOME="${AGENTS_HOME:-$HOME/.agents}"
AGENTS_DIR="$AGENTS_HOME/skills"
CLAUDE_PROFILES_HOME="${CLAUDE_PROFILES_HOME:-$HOME/.claude-profiles}"
LOCAL_BIN="$HOME/.local/bin"
MANAGER_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}/agent-manager"
MANAGER_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}/agent-manager"
MANAGER_STATE="$MANAGER_CONFIG_HOME/state.json"
MANAGER_CURRENT="$MANAGER_DATA_HOME/current"
BACKUP_ROOT="$MANAGER_DATA_HOME/backups"

DRY_RUN="${DRY_RUN:-0}"
_BACKUP_DIR=""
_FAILURES=0
_PENDING=0

# ---------- output ----------
if [ -t 1 ]; then
  C_RED=$'\033[31m'; C_GRN=$'\033[32m'; C_YEL=$'\033[33m'
  C_DIM=$'\033[2m';  C_BLD=$'\033[1m';  C_OFF=$'\033[0m'
else
  C_RED=''; C_GRN=''; C_YEL=''; C_DIM=''; C_BLD=''; C_OFF=''
fi

say()  { printf '%s\n' "$*"; }
ok()   { printf '  %sok%s   %s\n'   "$C_GRN" "$C_OFF" "$*"; }
info() { printf '  %s·%s    %s\n'   "$C_DIM" "$C_OFF" "$*"; }
warn() { printf '  %swarn%s %s\n'   "$C_YEL" "$C_OFF" "$*"; }
fail() { printf '  %sFAIL%s %s\n'   "$C_RED" "$C_OFF" "$*"; _FAILURES=$((_FAILURES+1)); }
head1(){ printf '\n%s%s%s\n' "$C_BLD" "$*" "$C_OFF"; }
failures() { return "$_FAILURES"; }
pending()  { return "$_PENDING"; }

# Prefix every mutating action in dry-run mode instead of doing it.
run() {
  if [ "$DRY_RUN" = 1 ]; then
    _PENDING=$((_PENDING+1))
    printf '  %sdry%s  %s\n' "$C_YEL" "$C_OFF" "$*"
  else
    "$@"
  fi
}

# mkdir -p that stays quiet (and counts no pending action) when the directory is already there.
ensure_dir() { [ -d "$1" ] || run mkdir -p "$1"; }

# Replace a managed path with an absolute link, archiving anything that is not already the
# expected link. Callers supply a stable backup label so different agent roots cannot collide.
link_managed() {
  local src="$1" dst="$2" label="${3:-$(basename "$2")}" target
  if [ -L "$dst" ]; then
    target="$(readlink "$dst")"
    if [ "$target" = "$src" ] && [ -e "$dst" ]; then
      info "$(shortp "$dst") already linked"
      return 0
    fi
    stash "$dst" "$label.symlink"
  elif [ -e "$dst" ]; then
    stash "$dst" "$label"
  fi
  ensure_dir "$(dirname "$dst")"
  run ln -s "$src" "$dst"
  ok "$(shortp "$dst") -> $(shortp "$src")"
}

# ---------- paths ----------
# Absolute target of a symlink, WITHOUT resolving the target any further.
# (realpath would collapse chains; we only want to make a relative link absolute.)
link_target_abs() {
  python3 - "$1" <<'PY'
import os, sys
p = sys.argv[1]
print(os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(p)), os.readlink(p))))
PY
}

expand_tilde() { case "$1" in "~"/*) printf '%s\n' "$HOME/${1#\~/}";; *) printf '%s\n' "$1";; esac; }

canonical_path() {
  python3 - "$1" <<'PY'
import os, sys
print(os.path.realpath(os.path.abspath(sys.argv[1])))
PY
}

entries_equal() {
  local left="$1" right="$2"
  [ "$(canonical_path "$left")" = "$(canonical_path "$right")" ] && return 0
  [ -f "$left" ] && [ -f "$right" ] && cmp -s "$left" "$right" && return 0
  [ -d "$left" ] && [ -d "$right" ] && diff -qr "$left" "$right" >/dev/null 2>&1
}

# ---------- manager root / accounts ----------

manager_active_root() {
  if [ -f "$MANAGER_STATE" ]; then
    jq -r '.activeRoot // empty' "$MANAGER_STATE" 2>/dev/null || true
  elif [ -L "$MANAGER_CURRENT" ] && [ -e "$MANAGER_CURRENT" ]; then
    canonical_path "$MANAGER_CURRENT"
  fi
}

manager_root_matches_repo() {
  local active
  active="$(manager_active_root)"
  [ -z "$active" ] || [ "$(canonical_path "$active")" = "$(canonical_path "$REPO")" ]
}

profile_names() {
  local list="$REPO/config/profiles.list"
  [ -f "$list" ] || return 0
  grep -vE '^[[:space:]]*(#|$)' "$list" 2>/dev/null || true
}

# All Claude skill roots. Codex's universal root is deliberately separate in this helper so
# callers can report the two product families clearly.
claude_skill_roots() {
  printf '%s\n' "$CLAUDE_DIR/skills"
  local name
  while read -r name; do
    [ -n "$name" ] && printf '%s\n' "$CLAUDE_PROFILES_HOME/$name/skills"
  done < <(profile_names)
}

all_skill_roots() {
  claude_skill_roots
  printf '%s\n' "$AGENTS_DIR"
}

# ---------- backups ----------
# One timestamped directory per run, created lazily so clean runs leave no litter.
# NB: this must never be called inside $(...) — the subshell would discard _BACKUP_DIR and
# every call would invent a fresh timestamp, scattering one run across many directories.
ensure_backup_dir() {
  [ -n "$_BACKUP_DIR" ] && return 0
  _BACKUP_DIR="$BACKUP_ROOT/migrate-$(date +%Y%m%d-%H%M%S)"
  run mkdir -p "$_BACKUP_DIR"
}

# Move a path into this run's backup directory. Never deletes.
stash() {
  local src="$1" label="${2:-$(basename "$1")}"
  ensure_backup_dir
  local dst="$_BACKUP_DIR/$label"
  run mkdir -p "$(dirname "$dst")"
  run mv "$src" "$dst"
  info "backed up $(shortp "$src") -> $(shortp "$dst")"
}

shortp() {
  case "$1" in
    "$HOME"/*) printf '~/%s\n' "${1#"$HOME"/}" ;;
    *)         printf '%s\n'   "$1" ;;
  esac
}

# ---------- vendor.json ----------
# Cached: these are called once per vendored skill inside several loops, and a jq spawn
# costs ~40ms here — enough to turn doctor.sh into a 20-second wait. vendor.json changes
# only in cmd_adopt, which drops the cache itself.
_VENDOR_NAMES_CACHE=""
_VENDOR_NAMES_LOADED=0
vendor_names() {
  if [ "$_VENDOR_NAMES_LOADED" = 0 ]; then
    _VENDOR_NAMES_CACHE="$(jq -r '.skills | keys[]' "$REPO/vendor.json")"
    _VENDOR_NAMES_LOADED=1
  fi
  [ -n "$_VENDOR_NAMES_CACHE" ] && printf '%s\n' "$_VENDOR_NAMES_CACHE"
  return 0
}
vendor_has() {
  case "
$(vendor_names)
" in
    *"
$1
"*) return 0 ;;
    *)  return 1 ;;
  esac
}
vendor_cache_drop() { _VENDOR_NAMES_CACHE=""; _VENDOR_NAMES_LOADED=0; }
vendor_field() { jq -r --arg n "$1" --arg f "$2" '.skills[$n][$f] // ""' "$REPO/vendor.json"; }

# Regenerate skills/.gitignore from vendor.json.
# No trailing slashes: git treats a symlink as a file, so "/diagnose/" would not match it.
write_skills_gitignore() {
  local out="$REPO/skills/.gitignore" tmp
  tmp="$(mktemp)"
  {
    echo "# Generated by \`agent-skills sync\` from vendor.json — do not edit by hand."
    echo "#"
    echo "# Everything listed here is fetched, not authored: a recipe in vendor.json can rebuild it."
    echo "# Anything in skills/ NOT listed here is repo-owned and tracked."
    echo "#"
    echo "# No trailing slashes — git treats a symlink as a file, so \"/name/\" would fail to match."
    echo
    vendor_names | sed 's|^|/|'
    echo
    echo "# noise"
    echo ".DS_Store"
    echo "__pycache__"
    echo
    echo "# Agent-owned, not authored here. ~/.claude/skills points at this registry, so"
    echo "# Claude Code syncs account skills into skills/synced/. It is re-downloadable,"
    echo "# must never be tracked, and has no SKILL.md -- doctor.sh skips what git ignores."
    echo "/synced"
  } > "$tmp"
  if [ "$DRY_RUN" = 1 ]; then
    if ! diff -q "$tmp" "$out" >/dev/null 2>&1; then
      printf '  %sdry%s  rewrite skills/.gitignore (%s entries)\n' "$C_YEL" "$C_OFF" "$(vendor_names | wc -l | tr -d ' ')"
    fi
    rm -f "$tmp"
  else
    mv "$tmp" "$out"
  fi
}

# ---------- mirror ----------
#
# mirror/ is the offline fallback: a frozen copy of every vendored skill, committed, read
# only when upstream cannot be reached. It is deliberately NOT on the live path — skills/
# keeps its symlinks — so a diff under mirror/ always means "upstream changed since I
# captured this", never the ambiguous "did I edit this?" that made vendoring copies a bad
# idea in the first place. See README, "When upstream disappears".

MIRROR_DIR="$REPO/mirror"
MIRROR_LOCK="$MIRROR_DIR/mirror.lock.json"

mirror_names() {
  [ -f "$MIRROR_LOCK" ] || return 0
  jq -r '.skills | keys[]' "$MIRROR_LOCK" 2>/dev/null || true
}
mirror_has() { [ -d "$MIRROR_DIR/$1" ]; }

# Paths inside a skill that are not worth mirroring (slides ships 6MB of example PNGs that
# do not compress and are not needed for the skill to run). Recorded in the lock so the
# omission is visible rather than silent.
vendor_excludes() {
  jq -r --arg n "$1" '.skills[$n].mirrorExclude // [] | .[]' "$REPO/vendor.json" 2>/dev/null || true
}

# Where a vendored skill's REAL files live. skills/<name> is either a symlink into
# ~/.agents/skills (skills-cli), a real clone (git), or a directory holding one symlink
# (local) — resolving the top level covers all three, and cp -RL resolves the rest.
mirror_source_dir() {
  local cur="$REPO/skills/$1"
  if [ -L "$cur" ]; then link_target_abs "$cur"
  elif [ -d "$cur" ]; then printf '%s\n' "$cur"
  else return 1
  fi
}

# Copy a skill's real files into mirror/<name>, dropping VCS metadata, caches and excludes.
# Never a symlink: the whole point is that this copy survives its source disappearing.
mirror_capture() {
  local name="$1" src dst ex
  src="$(mirror_source_dir "$name")" || { warn "$name: not present in skills/ — nothing to mirror"; return 1; }
  [ -e "$src" ] || { warn "$name: $(shortp "$src") is dangling — nothing to mirror"; return 1; }
  dst="$MIRROR_DIR/$name"

  if [ "$DRY_RUN" = 1 ]; then run "mirror $name from $(shortp "$src")"; return 0; fi

  rm -rf "$dst"
  mkdir -p "$(dirname "$dst")"
  cp -RL "$src" "$dst" 2>/dev/null || cp -R "$src" "$dst"

  rm -rf "$dst/.git"
  find "$dst" \( -name '.DS_Store' -o -name '__pycache__' -o -name '*.pyc' \) -exec rm -rf {} + 2>/dev/null || true
  while read -r ex; do
    [ -z "$ex" ] && continue
    rm -rf "${dst:?}/$ex"
  done < <(vendor_excludes "$name")
  return 0
}

mirror_captured_at() {
  [ -f "$MIRROR_LOCK" ] || { printf 'unknown\n'; return 0; }
  jq -r --arg n "$1" '.skills[$n].capturedAt // "unknown"' "$MIRROR_LOCK" 2>/dev/null || printf 'unknown\n'
}

# Bytes and file count of a mirrored skill, for the lock.
mirror_stat_files() { find "$MIRROR_DIR/$1" -type f 2>/dev/null | wc -l | tr -d ' '; }
mirror_stat_bytes() { du -sk "$MIRROR_DIR/$1" 2>/dev/null | cut -f1 | tr -d ' '; }
