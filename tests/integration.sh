#!/usr/bin/env bash
set -euo pipefail

SOURCE_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_ROOT="$(mktemp -d)"
TEST_HOME="$TEST_ROOT/home"
FIXTURE="$TEST_ROOT/claude-manager"
STUB_BIN="$TEST_ROOT/bin"
mkdir -p "$TEST_HOME" "$STUB_BIN"
cp -R "$SOURCE_REPO/." "$FIXTURE/"

# Tests focus on authored-skill topology. Vendor restoration has its own committed mirror and
# would otherwise contact the network or retain this machine's absolute ignored symlinks.
while read -r vendor_name; do
  if [ -n "$vendor_name" ]; then
    rm -rf "$FIXTURE/skills/$vendor_name"
    rm -rf "$FIXTURE/mirror/$vendor_name"
  fi
done < <(jq -r '.skills | keys[]' "$FIXTURE/vendor.json")
jq '.skills = {}' "$FIXTURE/vendor.json" > "$TEST_ROOT/vendor.json"
mv "$TEST_ROOT/vendor.json" "$FIXTURE/vendor.json"
jq '.skills = {}' "$FIXTURE/mirror/mirror.lock.json" > "$TEST_ROOT/mirror.json"
mv "$TEST_ROOT/mirror.json" "$FIXTURE/mirror/mirror.lock.json"
rm -f "$FIXTURE/secrets.env"
cp "$FIXTURE/secrets.env.example" "$FIXTURE/secrets.env"

printf '%s\n' '#!/usr/bin/env bash' \
  'case "${1:-}" in' \
  '  plugin) [ "${2:-}" = list ] && echo "[]";;' \
  '  mcp) exit 1;;' \
  'esac' \
  'exit 0' > "$STUB_BIN/claude"
printf '%s\n' '#!/usr/bin/env bash' \
  'if [ "${1:-}" = plugin ] && [ "${2:-}" = list ]; then echo '\''{"installed":[],"available":[]}'\''; fi' \
  'if [ "${1:-}" = mcp ] && [ "${2:-}" = get ]; then exit 1; fi' \
  'exit 0' > "$STUB_BIN/codex"
printf '%s\n' '#!/usr/bin/env bash' 'exit 0' > "$STUB_BIN/npx"
chmod +x "$STUB_BIN/claude" "$STUB_BIN/codex" "$STUB_BIN/npx"

export HOME="$TEST_HOME"
export PATH="$STUB_BIN:$PATH"
export XDG_CONFIG_HOME="$TEST_HOME/.config"
export XDG_DATA_HOME="$TEST_HOME/.local/share"
mkdir -p "$HOME/.codex"
printf '%s\n' 'model = "old-model"' '[projects."/tmp/example"]' 'trust_level = "trusted"' > "$HOME/.codex/config.toml"
printf 'source %s/shell/claude.zsh\n' "$FIXTURE" > "$HOME/.zshrc"

# Existing agent-specific skills are migrated into the one canonical registry.
mkdir -p "$HOME/.agents/skills/codex-seed" "$HOME/.claude/skills/claude-seed"
printf '%s\n' '---' 'name: codex-seed' 'description: Existing Codex skill.' '---' > "$HOME/.agents/skills/codex-seed/SKILL.md"
printf '%s\n' '---' 'name: claude-seed' 'description: Existing Claude skill.' '---' > "$HOME/.claude/skills/claude-seed/SKILL.md"

# Differing skills with the same name are never silently merged or overwritten.
mkdir -p "$HOME/.agents/skills/conflict" "$HOME/.claude/skills/conflict"
printf '%s\n' '---' 'name: conflict' 'description: Codex version.' '---' > "$HOME/.agents/skills/conflict/SKILL.md"
printf '%s\n' '---' 'name: conflict' 'description: Claude version.' '---' > "$HOME/.claude/skills/conflict/SKILL.md"
if "$FIXTURE/install.sh" --offline >/dev/null 2>&1; then
  echo "install unexpectedly accepted conflicting live skills" >&2
  exit 1
fi
grep -q 'Codex version' "$HOME/.agents/skills/conflict/SKILL.md"
grep -q 'Claude version' "$HOME/.claude/skills/conflict/SKILL.md"
rm -rf "$HOME/.agents/skills/conflict" "$HOME/.claude/skills/conflict"

"$FIXTURE/install.sh" --offline

CURRENT="$XDG_DATA_HOME/agent-manager/current"
[ "$(readlink "$CURRENT")" = "$FIXTURE" ]
[ "$(readlink "$HOME/.claude/skills")" = "$CURRENT/skills" ]
[ "$(readlink "$HOME/.agents/skills")" = "$CURRENT/skills" ]
[ "$(readlink "$HOME/.claude-profiles/claude2/skills")" = "$CURRENT/skills" ]
[ "$(readlink "$HOME/.claude-profiles/claude3/skills")" = "$CURRENT/skills" ]
[ -d "$HOME/.codex/skills" ] || true  # manager must neither require nor replace this path

grep -q '^# >>> agent-manager managed defaults >>>$' "$HOME/.codex/config.toml"
grep -q '^model = "gpt-5.6-sol"$' "$HOME/.codex/config.toml"
grep -q '^\[projects."/tmp/example"\]$' "$HOME/.codex/config.toml"
if python3 -c 'import tomllib' >/dev/null 2>&1; then
  python3 -c 'import tomllib; tomllib.load(open("'$HOME'/.codex/config.toml", "rb"))'
fi

"$FIXTURE/bin/agent-skills" create shared-test --scope global >/dev/null
[ -f "$FIXTURE/skills/shared-test/SKILL.md" ]
[ -f "$HOME/.claude/skills/shared-test/SKILL.md" ]
[ -f "$HOME/.agents/skills/shared-test/SKILL.md" ]
[ -f "$FIXTURE/skills/codex-seed/SKILL.md" ]
[ -f "$FIXTURE/skills/claude-seed/SKILL.md" ]
grep -qxF "source $CURRENT/shell/agents.zsh" "$HOME/.zshrc"
! grep -q 'claude-manager/shell/claude.zsh' "$HOME/.zshrc"

"$FIXTURE/bin/claude-account" add claude4 --model sonnet >/dev/null
[ "$(readlink "$HOME/.claude-profiles/claude4/skills")" = "$CURRENT/skills" ]
[ "$(readlink "$HOME/.claude-profiles/claude4/CLAUDE.md")" = "$CURRENT/config/shared/instructions.md" ]

PROJECT="$TEST_ROOT/project"
mkdir -p "$PROJECT"
"$FIXTURE/bin/agent-manager" project init "$PROJECT" >/dev/null
"$FIXTURE/bin/agent-skills" create project-test --scope project --project "$PROJECT" >/dev/null
[ -f "$PROJECT/.agents/skills/project-test/SKILL.md" ]
[ -L "$PROJECT/.claude/skills" ]
[ "$(readlink "$PROJECT/.claude/skills")" = '../.agents/skills' ]
[ -f "$PROJECT/.claude/skills/project-test/SKILL.md" ]
[ -L "$PROJECT/CLAUDE.md" ]
[ "$(readlink "$PROJECT/CLAUDE.md")" = 'AGENTS.md' ]
mkdir -p "$PROJECT/.claude/skills/claude-direct"
printf '%s\n' '---' 'name: claude-direct' 'description: Written through Claude.' '---' > "$PROJECT/.claude/skills/claude-direct/SKILL.md"
[ -f "$PROJECT/.agents/skills/claude-direct/SKILL.md" ]

LEGACY_PROJECT="$TEST_ROOT/legacy-project"
mkdir -p "$LEGACY_PROJECT/.claude/skills/legacy-skill"
printf '%s\n' '---' 'name: legacy-skill' 'description: Existing project skill.' '---' > "$LEGACY_PROJECT/.claude/skills/legacy-skill/SKILL.md"
"$FIXTURE/bin/agent-manager" project init "$LEGACY_PROJECT" >/dev/null
[ -L "$LEGACY_PROJECT/.agents/skills" ]
[ -f "$LEGACY_PROJECT/.agents/skills/legacy-skill/SKILL.md" ]

# Reconciliation is idempotent and keeps the portable Codex project table.
before="$(shasum -a 256 "$HOME/.codex/config.toml" | cut -d' ' -f1)"
"$FIXTURE/install.sh" --offline
after="$(shasum -a 256 "$HOME/.codex/config.toml" | cut -d' ' -f1)"
[ "$before" = "$after" ]

"$FIXTURE/doctor.sh"

# Switching checkouts is explicit, refuses a dirty active checkout, and keeps every live
# link stable through the machine-local `current` indirection.
SECOND="$TEST_ROOT/manager-two"
cp -R "$FIXTURE/." "$SECOND/"
rm -rf "$SECOND/.git"
if "$FIXTURE/bin/agent-manager" root switch "$SECOND" >/dev/null 2>&1; then
  echo "root switch unexpectedly accepted a dirty active checkout" >&2
  exit 1
fi
rm -rf "$FIXTURE/.git"
"$FIXTURE/bin/agent-manager" root switch "$SECOND" >/dev/null
SECOND_REAL="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$SECOND")"
[ "$(readlink "$CURRENT")" = "$SECOND_REAL" ]
[ "$(jq -r '.activeRoot' "$XDG_CONFIG_HOME/agent-manager/state.json")" = "$SECOND_REAL" ]
[ -f "$HOME/.claude/skills/shared-test/SKILL.md" ]
[ -f "$HOME/.agents/skills/shared-test/SKILL.md" ]

echo "integration: ok"
