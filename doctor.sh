#!/usr/bin/env bash
#
# doctor.sh — verify the installation. Read-only; changes nothing.
# Exits non-zero if anything is broken, so it works in CI.
#
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$REPO/lib/common.sh"
# shellcheck source=lib/agents/claude.sh
source "$REPO/lib/agents/claude.sh"
# shellcheck source=lib/agents/codex.sh
source "$REPO/lib/agents/codex.sh"

PORTABLE=0
for arg in "$@"; do
  case "$arg" in --portable) PORTABLE=1 ;; -h|--help) echo "usage: ./doctor.sh [--portable]"; exit 0 ;; *) echo "unknown flag: $arg" >&2; exit 2 ;; esac
done

# Several checks below read `git ls-files`, which returns NOTHING until the first commit.
# Ungated, they print ok for the wrong reason: "no secret file is tracked" is trivially true
# when nothing at all is tracked, which is exactly when you most want the guard to mean
# something. Gate them on a commit actually existing and say so when it does not.
HAS_COMMIT=0
[ -d "$REPO/.git" ] && git -C "$REPO" rev-parse --verify HEAD >/dev/null 2>&1 && HAS_COMMIT=1

# ---------------------------------------------------------------- active checkout

head1 "Active manager checkout"
active="$(manager_active_root)"
if [ -z "$active" ]; then
  fail "no active root recorded — run ./install.sh"
elif [ "$(canonical_path "$active")" != "$(canonical_path "$REPO")" ]; then
  fail "this clone is not active (active: $(shortp "$active"))"
elif [ ! -L "$MANAGER_CURRENT" ] || [ "$(canonical_path "$MANAGER_CURRENT")" != "$(canonical_path "$REPO")" ]; then
  fail "$(shortp "$MANAGER_CURRENT") does not resolve to this checkout"
else
  ok "active root: $(shortp "$REPO")"
fi

# ---------------------------------------------------------------- managed directories

head1 "Shared skill roots"
claude_adapter_doctor || true
codex_adapter_doctor || true

head1 "Claude-only directories"
for d in commands agents; do
  live="$CLAUDE_DIR/$d"
  if [ ! -L "$live" ]; then
    fail "$(shortp "$live") is not a symlink — run ./install.sh"
  elif [ "$(readlink "$live")" != "$MANAGER_CURRENT/$d" ]; then
    fail "$(shortp "$live") -> $(shortp "$(readlink "$live")") (expected the active checkout)"
  elif [ ! -d "$live/" ]; then
    fail "$(shortp "$live") is dangling"
  else
    ok "$d -> repo"
  fi
done

# ---------------------------------------------------------------- the relative-symlink hazard

head1 "Symlink health in skills/"
dangling=0; relative=0
for e in "$REPO"/skills/*; do
  [ -L "$e" ] || continue
  t="$(readlink "$e")"
  case "$t" in /*) ;; *) fail "$(basename "$e") has a RELATIVE target ($t) — it will break"; relative=$((relative+1)) ;; esac
  [ -e "$e" ] || { fail "$(basename "$e") is DANGLING -> $t"; dangling=$((dangling+1)); }
done
[ "$dangling" = 0 ] && [ "$relative" = 0 ] && ok "every vendored link is absolute and resolves"

# Nested symlinks (browser/SKILL.md) must resolve too.
for e in "$REPO"/skills/*/*; do
  [ -L "$e" ] || continue
  [ -e "$e" ] || fail "${e#$REPO/} is DANGLING -> $(readlink "$e")"
done

head1 "Skill metadata"
seen_names=""
skill_errors=0
for skill_dir in "$REPO"/skills/*; do
  [ -d "$skill_dir" ] || continue
  if [ -d "$REPO/.git" ] && git -C "$REPO" check-ignore -q "${skill_dir#$REPO/}" 2>/dev/null; then
    continue
  fi
  skill_name="$(basename "$skill_dir")"
  skill_file="$skill_dir/SKILL.md"
  if [ ! -f "$skill_file" ]; then
    # Name both remedies. skills/ is shared now: ~/.claude/skills points here, so an agent
    # can drop a directory of its own in. Without this hint the only obvious fix looks like
    # deleting it -- which, for agent-synced skills, destroys live content.
    fail "$skill_name has no SKILL.md — if an agent owns it, add it to the noise list in lib/common.sh; if it is yours, give it a SKILL.md"
    skill_errors=$((skill_errors+1))
    continue
  fi
  declared="$(awk 'NR <= 20 && /^name:[[:space:]]*/ {sub(/^name:[[:space:]]*/, ""); print; exit}' "$skill_file")"
  if [ -z "$declared" ]; then
    fail "$skill_name/SKILL.md has no frontmatter name"
    skill_errors=$((skill_errors+1))
  elif [ "$declared" != "$skill_name" ]; then
    fail "$skill_name declares name '$declared'"
    skill_errors=$((skill_errors+1))
  elif printf '%s\n' "$seen_names" | grep -qxF "$declared"; then
    fail "duplicate skill name '$declared'"
    skill_errors=$((skill_errors+1))
  else
    seen_names="${seen_names}${seen_names:+$'\n'}$declared"
  fi
done
[ "$skill_errors" = 0 ] && ok "every skill has a unique matching frontmatter name"

# ---------------------------------------------------------------- vendor / ownership split

head1 "Ownership split"
missing=0
while read -r n; do
  [ -e "$REPO/skills/$n" ] || [ -L "$REPO/skills/$n" ] || { fail "$n is in vendor.json but absent — run: agent-skills sync"; missing=$((missing+1)); }
done < <(vendor_names)
  [ "$missing" = 0 ] && ok "all $(vendor_names | wc -l | tr -d ' ') vendored skills present"

if [ -d "$REPO/.git" ]; then
  if [ "$HAS_COMMIT" = 0 ]; then
    info "tracked-symlink and ownership checks — not yet meaningful, repo has no commit"
  else
    bad="$(git -C "$REPO" ls-files -s skills/ | awk '$1==120000 {print $4}')"
    if [ -n "$bad" ]; then
      fail "symlinks are TRACKED in git (they will break on another machine):"
      printf '        %s\n' $bad
    else
      ok "no symlink is tracked"
    fi
    owned="$(git -C "$REPO" ls-files skills/ | cut -d/ -f2 | grep -v '^\.' | sort -u | tr '\n' ' ')"
    ok "repo-owned skills: ${owned:-<none>}"
  fi
fi

# ---------------------------------------------------------------- executables & config

head1 "Executables"
for f in "$REPO"/bin/*; do
  n="$(basename "$f")"; d="$LOCAL_BIN/$n"; expected="$MANAGER_CURRENT/bin/$n"
  if [ -L "$d" ] && [ "$(readlink "$d")" = "$expected" ]; then ok "$n"
  elif [ -e "$d" ]; then fail "$n in $(shortp "$LOCAL_BIN") is not linked to the repo"
  else fail "$n missing from $(shortp "$LOCAL_BIN") — run ./install.sh"; fi
done
for n in claude2 claude3; do
  [ -e "$LOCAL_BIN/$n" ] && warn "$n shim still present — obsolete, install.sh will retire it"
done

head1 "Config"
# Not just "is a symlink": a link pointing anywhere else, or a dangling one, passes that
# test while your edits quietly stop reaching the repo. Check the target and that it resolves.
_cmd="$CLAUDE_DIR/CLAUDE.md"
if [ ! -L "$_cmd" ]; then
  if [ -f "$_cmd" ]; then fail "CLAUDE.md is a real file, not the repo symlink — run: agent-manager pull"
  else fail "CLAUDE.md is missing — run ./install.sh"; fi
elif [ "$(readlink "$_cmd")" != "$MANAGER_CURRENT/config/shared/instructions.md" ]; then
  fail "CLAUDE.md -> $(shortp "$(readlink "$_cmd")") (expected shared instructions)"
elif [ ! -e "$_cmd" ]; then
  fail "CLAUDE.md link is dangling"
else
  ok "CLAUDE.md -> shared instructions"
fi

if [ -f "$CODEX_DIR/config.toml" ] && grep -q '^# >>> agent-manager managed defaults >>>$' "$CODEX_DIR/config.toml"; then
  if python3 -c 'import tomllib' >/dev/null 2>&1; then
    python3 -c 'import sys,tomllib; tomllib.load(open(sys.argv[1], "rb"))' "$CODEX_DIR/config.toml" 2>/dev/null \
      && ok "Codex config is valid and has managed defaults" \
      || fail "Codex config.toml is invalid"
  else
    ok "Codex config has managed defaults (full TOML validation needs Python 3.11+)"
  fi
else
  fail "Codex portable defaults are not installed"
fi

[ -f "$REPO/secrets.env" ] && ok "secrets.env present" || warn "secrets.env missing — copy secrets.env.example"

# ---------------------------------------------------------------- mirror
#
# The mirror is the last line of defence when upstream disappears. A gap in it is silent
# until the day you actually need it, which is the worst time to discover one.

head1 "Offline mirror"
if [ ! -f "$MIRROR_LOCK" ]; then
  fail "mirror/mirror.lock.json missing — run: agent-skills mirror"
else
  gap=0
  while read -r n; do
    [ -z "$n" ] && continue
    mirror_has "$n" || { fail "$n has no mirror/ copy — run: agent-skills mirror"; gap=$((gap+1)); }
  done < <(vendor_names)

  stale=0
  for d in "$MIRROR_DIR"/*/; do
    [ -d "$d" ] || continue
    b="$(basename "$d")"
    vendor_has "$b" || { warn "mirror/$b is no longer in vendor.json — run: agent-skills mirror --prune"; stale=$((stale+1)); }
  done

  if [ "$gap" = 0 ] && [ "$stale" = 0 ]; then
    ok "mirror covers all $(vendor_names | wc -l | tr -d ' ') vendored skills ($(du -sh "$MIRROR_DIR" | cut -f1 | tr -d ' '))"
  fi
fi

# ---------------------------------------------------------------- safety

head1 "Credential safety"
if [ -d "$REPO/.git" ]; then
  if [ "$HAS_COMMIT" = 0 ]; then
    info "no secret file is tracked — not yet meaningful, repo has no commit"
  else
    leaked="$(git -C "$REPO" ls-files | grep -E '(^|/)(secrets\.env|glm\.json|glm-2\.json)$' || true)"
    [ -n "$leaked" ] && fail "TRACKED SECRET FILE: $leaked" || ok "no secret file is tracked"
  fi
  hk="$REPO/.git/hooks/pre-commit"
  if [ -x "$hk" ] || [ -L "$hk" ]; then ok "pre-commit guard installed"; else fail "pre-commit guard missing"; fi
fi

head1 "Shell"
if grep -qF "source $MANAGER_CURRENT/shell/agents.zsh" "$HOME/.zshrc" 2>/dev/null; then
  ok ".zshrc sources the stable agent-manager entrypoint"
elif grep -qE "^[[:space:]]*(source|\.)[[:space:]]+.*claude-manager/shell/claude\.zsh" "$HOME/.zshrc" 2>/dev/null; then
  warn ".zshrc uses the compatibility Claude entrypoint; install.sh can migrate it"
else
  fail ".zshrc does not source shell/claude.zsh"
fi
for legacy in 'claude2() {' 'claude3() {' '_apply_claude_mode()'; do
  grep -qF "$legacy" "$HOME/.zshrc" 2>/dev/null && warn "legacy definition still in .zshrc: $legacy"
done

# ---------------------------------------------------------------- accounts
#
# profiles.list drives shell/claude.zsh, which eval-defines one function per line. A bad
# name there produces a broken function in every future shell, so validate it here.

head1 "Accounts"
RESERVED_NAMES="claude clauded claudep cskills use-glm use-claude claude-account claude-skills claude-profile claude-mcp-sync agent-manager agent-skills"
acct_n=0
while read -r a; do
  [ -z "$a" ] && continue
  case "$a" in \#*) continue ;; esac
  acct_n=$((acct_n+1))
  if ! printf '%s' "$a" | grep -qE '^[a-z][a-z0-9-]*$'; then
    fail "'$a' in profiles.list is not a valid account name"
    continue
  fi
  case " $RESERVED_NAMES " in *" $a "*) fail "'$a' in profiles.list is a reserved name"; continue ;; esac
  if [ -f "$REPO/config/profiles/$a.json" ]; then
    if jq -e . "$REPO/config/profiles/$a.json" >/dev/null 2>&1; then
      ok "$a  ($(jq -r '.model // "no model"' "$REPO/config/profiles/$a.json"))"
    else
      fail "$a: config/profiles/$a.json is not valid JSON"
    fi
  else
    warn "$a has no overlay in config/profiles/ — it will use whatever defaults it picks up"
  fi
done < "$REPO/config/profiles.list"
ok "primary: claude / clauded    profiles: $acct_n"
info "manage with: claude-account list | add <name> | remove <name>"

# ---------------------------------------------------------------- claude binary
#
# Every entry point (claude, clauded, and each profile via bin/claude-profile's
# `exec claude`) resolves the bare name `claude` through PATH. So there is exactly one
# signpost — ~/.local/bin/claude -> ~/.local/share/claude/versions/<ver> — and all
# accounts inherit whatever it points at.
#
# Two ways that breaks, both seen in the wild:
#   1. `npm install -g @anthropic-ai/claude-code` ships the same native binary, but its
#      postinstall REPOINTS the signpost at its own version and lands earlier on PATH.
#      It silently reverts a native upgrade. Native and npm must not coexist.
#   2. The native updater writes a new versions/ entry but the signpost still names an
#      older one, so the download is orphaned and every account keeps running stale.

head1 "Claude binary"
CLAUDE_LINK="$HOME/.local/bin/claude"
CLAUDE_VERSIONS="$HOME/.local/share/claude/versions"

if [ ! -d "$CLAUDE_VERSIONS" ]; then
  info "no native install at $(shortp "$CLAUDE_VERSIONS") — skipping binary checks"
else
  # --- the signpost names the newest version actually on disk
  newest="$(ls -1 "$CLAUDE_VERSIONS" 2>/dev/null | grep -E '^[0-9]+(\.[0-9]+)+$' | sort -V | tail -1)"
  if [ ! -L "$CLAUDE_LINK" ]; then
    fail "$(shortp "$CLAUDE_LINK") is not a symlink — run: claude install latest"
  elif [ ! -x "$CLAUDE_LINK" ]; then
    fail "$(shortp "$CLAUDE_LINK") is dangling -> $(shortp "$(readlink "$CLAUDE_LINK")")"
  else
    linked="$(basename "$(readlink "$CLAUDE_LINK")")"
    if [ -n "$newest" ] && [ "$linked" != "$newest" ]; then
      fail "signpost is stale: claude -> $linked but $newest is on disk — run: claude install latest"
    else
      ok "signpost -> $linked (newest on disk)"
    fi
  fi

  # --- nothing shadows the signpost: what PATH actually runs must match what it names
  if [ -x "$CLAUDE_LINK" ]; then
    want="$("$CLAUDE_LINK" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
    got="$(command claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
    if [ -z "$got" ]; then
      fail "\`claude\` is not runnable from PATH"
    elif [ -n "$want" ] && [ "$want" != "$got" ]; then
      fail "PATH runs $got but the signpost names $want — something earlier on PATH shadows it"
    else
      ok "PATH resolves to $got"
    fi
  fi

  # --- no npm-installed copy anywhere, since it re-clobbers the signpost on every install
  npm_copies=""
  if command -v npm >/dev/null 2>&1; then
    npm_prefix="$(npm prefix -g 2>/dev/null)"
    [ -n "$npm_prefix" ] && [ -e "$npm_prefix/lib/node_modules/@anthropic-ai/claude-code" ] \
      && npm_copies="$npm_copies $npm_prefix/lib/node_modules/@anthropic-ai/claude-code"
  fi
  # mise keeps a separate global bin per node version, and a shim dir that may be off PATH
  # today but comes back the moment shim mode is enabled.
  for cand in "$HOME"/.local/share/mise/installs/node/*/lib/node_modules/@anthropic-ai/claude-code \
              "$HOME"/.local/share/mise/shims/claude; do
    [ -e "$cand" ] || continue
    # mise exposes one install under many aliases (22, 22.14, latest, lts...); resolve to
    # the real path so a single copy is not reported seven times.
    real="$(canonical_path "$cand")"
    case " $npm_copies " in *" $real "*) continue ;; esac
    npm_copies="$npm_copies $real"
  done
  if [ -n "$npm_copies" ]; then
    fail "npm-managed Claude still present — it will clobber the signpost on its next install:"
    for c in $npm_copies; do info "$(shortp "$c")"; done
    info "remove with: npm uninstall -g @anthropic-ai/claude-code"
  else
    ok "no npm-managed copy (native installer owns the binary)"
  fi

  # --- self-updates on for primary AND every profile; claude-profile does not mirror these
  stale_cfg=""
  for cfg in "$HOME/.claude.json" "$HOME"/.claude-profiles/*/.claude.json; do
    [ -f "$cfg" ] || continue
    command -v jq >/dev/null 2>&1 || break
    jq -e '(.autoUpdates == false) or (.installMethod == "global")' "$cfg" >/dev/null 2>&1 \
      && stale_cfg="$stale_cfg $cfg"
  done
  if [ -n "$stale_cfg" ]; then
    warn "these configs will not self-update (autoUpdates false, or still installMethod global):"
    for c in $stale_cfg; do info "$(shortp "$c")"; done
  else
    ok "self-updates enabled for primary and all profiles"
  fi

  # --- superseded versions are ~200-320MB each
  keep=2
  n_ver="$(ls -1 "$CLAUDE_VERSIONS" 2>/dev/null | grep -cE '^[0-9]+(\.[0-9]+)+$')"
  if [ "${n_ver:-0}" -gt "$keep" ]; then
    info "$n_ver versions on disk ($(du -sh "$CLAUDE_VERSIONS" 2>/dev/null | cut -f1 | tr -d ' ')) — only the newest is in use"
  fi
fi

# ---------------------------------------------------------------- portable clone readiness

head1 "Clone portability"
if [ -d "$REPO/.git" ] && git -C "$REPO" rev-parse --verify HEAD >/dev/null 2>&1; then
  ok "Git has a commit"
else
  [ "$PORTABLE" = 1 ] && fail "Git has no commit" || warn "Git has no commit yet"
fi
if [ -d "$REPO/.git" ] && [ -n "$(git -C "$REPO" remote 2>/dev/null)" ]; then
  ok "Git remote configured"
else
  [ "$PORTABLE" = 1 ] && fail "Git has no remote" || warn "Git has no remote yet"
fi
# An absolute home path leaks the author's username and breaks the clone on any other machine.
# Scope = what git would actually COMMIT, not the working tree: skills/.trash and
# skills/*-workspace legitimately hold real paths and are gitignored, so walking the
# filesystem would fail on content that never ships. Username-shaped on purpose
# ([a-z]...) so this pattern does not match its own definition here.
_abs_pat='/Users/[a-z][a-z0-9_.-]*/'
# Documentation placeholders are the convention, not a leak.
_abs_skip='/Users/(me|name|you|user|username)/'
if [ -d "$REPO/.git" ]; then
  _abs_hits="$(cd "$REPO" && git ls-files -co --exclude-standard -z 2>/dev/null \
    | xargs -0 grep -nIE "$_abs_pat" 2>/dev/null | grep -vE "$_abs_skip" \
    | cut -d: -f1 | sort -u)"
else
  _abs_hits="$(grep -RnIE "$_abs_pat" "$REPO/config" "$REPO/shell" "$REPO/bin" "$REPO/lib" 2>/dev/null \
    | grep -vE "$_abs_skip" | cut -d: -f1 | sort -u)"
fi
if [ -n "$_abs_hits" ]; then
  fail "absolute user path in committable source — replace with ~ or a \${VAR}:"
  printf '        %s\n' $_abs_hits
else
  ok "no absolute user path in committable source"
fi

# ---------------------------------------------------------------- result

head1 "Result"
if failures; then
  ok "healthy"
  [ -d "$REPO/.git" ] && [ -n "$(git -C "$REPO" status --porcelain)" ] && info "uncommitted changes — review with: git -C $(shortp "$REPO") status"
  exit 0
else
  fail_count=$?
  say "  ${C_RED}$fail_count problem(s) — run ./install.sh, then ./bin/agent-skills sync${C_OFF}"
  exit 1
fi
