# The one list of token shapes that must never reach a commit.
#
# Sourced by hooks/pre-commit (scans the staged diff) and bin/claude-manager (scans files on
# disk). Keeping one copy matters: two lists drift, and the half that goes stale is the one
# that lets a token through.
#
# Safe to source under `set -euo pipefail`.

CREDSCAN_PATTERNS=(
  'sk-ant-[A-Za-z0-9_-]{20,}'                 # Anthropic API key
  'ark-[0-9a-f]{8}-[0-9a-f-]{20,}'            # BytePlus ark token
  'gh[pousr]_[A-Za-z0-9]{20,}'                # GitHub token
  'bu_[A-Za-z0-9_-]{20,}'                     # browser-use key
  'AKIA[0-9A-Z]{16}'                          # AWS access key
  '"ANTHROPIC_AUTH_TOKEN"[[:space:]]*:[[:space:]]*"[^$"]'   # a literal, not a ${VAR}
  '[0-9a-f]{32}\.[A-Za-z0-9]{16}'             # z.ai style <hex32>.<id>
)

# Files that hold rendered, live credentials. They are gitignored, but .gitignore alone is
# one `git add -f` away from being wrong.
CREDSCAN_SECRET_FILES='(^|/)(secrets\.env|glm\.json|glm-2\.json)$'

# secrets.env.example documents every key by shape, so it necessarily contains strings that
# match the patterns above — `bu_xxxxxxxx…` and friends. Without this the guard would block
# the one file whose whole job is to be committed. Only obvious fillers qualify.
CREDSCAN_PLACEHOLDER='(xxxxxxxx|XXXXXXXX|YOUR_|REPLACE_ME|CHANGEME|<[A-Za-z0-9_-]+>)'

# Drop placeholder matches; print what is left. Used by both scanners.
_credscan_real() { grep -vE "$CREDSCAN_PLACEHOLDER" || true; }

_credscan_redact() { sed 's/\(.\{12\}\).*/\1…(redacted)/' | sort -u | sed 's/^/  found:   /'; }

# credscan <<< "$text"
#
# Scans text on stdin — the staged diff, for the hook. Reports matches to stderr, redacted
# after 12 characters: enough to recognise which key it is, not enough to be a leak itself.
# Returns 0 when clean, 1 when anything matched.
#
# NB: plain ERE via grep -E throughout. BSD grep rejects '\+' as a BRE repetition operator
# with no operand, errors out, and silently skips the filter — which is how a guard like
# this fails open.
credscan() {
  local text p found hits=0
  text="$(cat)"
  [ -z "$text" ] && return 0

  for p in "${CREDSCAN_PATTERNS[@]}"; do
    found="$(printf '%s\n' "$text" | grep -oE "$p" 2>/dev/null | _credscan_real)"
    if [ -n "$found" ]; then
      printf '  pattern: %s\n' "$p" >&2
      printf '%s\n' "$found" | _credscan_redact >&2
      hits=$((hits+1))
    fi
  done

  if [ "$hits" -gt 0 ]; then return 1; fi
  return 0
}

# credscan_files <<< "$newline_separated_paths"
#
# Scans files on disk. Preferred over piping their contents into `credscan`: grep reads the
# files itself, so nothing has to survive a round trip through a shell variable, `-I` skips
# binaries outright, and every hit names the file it came from.
# Returns 0 when clean, 1 when anything matched.
credscan_files() {
  local p f found hits=0
  local -a files=()
  while IFS= read -r f; do
    [ -n "$f" ] && [ -f "$f" ] && files+=("$f")
  done
  [ "${#files[@]}" -eq 0 ] && return 0

  for p in "${CREDSCAN_PATTERNS[@]}"; do
    found="$(grep -IHoEs -- "$p" "${files[@]}" 2>/dev/null | _credscan_real)"
    if [ -n "$found" ]; then
      printf '  pattern: %s\n' "$p" >&2
      printf '%s\n' "$found" | sed 's/:\(.\{12\}\).*/:  \1…(redacted)/' | sort -u | sed 's/^/  in:      /' >&2
      hits=$((hits+1))
    fi
  done

  if [ "$hits" -gt 0 ]; then return 1; fi
  return 0
}

# credscan_paths <<< "$newline_separated_paths"
# Prints any path that is a rendered secret file. Returns 0 when clean, 1 otherwise.
credscan_paths() {
  local hit
  hit="$(grep -E "$CREDSCAN_SECRET_FILES" || true)"
  if [ -n "$hit" ]; then
    printf '%s\n' "$hit" | sed 's/^/  /' >&2
    return 1
  fi
  return 0
}
