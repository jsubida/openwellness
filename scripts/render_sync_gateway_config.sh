#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# render_sync_gateway_config.sh
#
# DESCRIPTION:
#   Renders the git-tracked Sync Gateway config template into the gitignored
#   runtime config that the `sync-gateway` compose service bind-mounts:
#
#     sync_gateway/sync_gateway.json.template  (tracked, no secrets)
#         -- envsubst, values from .env -->
#     sync_gateway/sync_gateway.json           (gitignored, carries secrets)
#
#   The template/rendered split is the same convention opserver uses for
#   mongo/mongod.conf and load_balancer/api.conf (see opserver's
#   environment.sh): credentials live in .env only and never enter git.
#
#   Every ${VARIABLE} the template references is required to be present and
#   non-empty in .env BEFORE substitution, because envsubst silently replaces
#   an unset variable with the empty string. An empty bucket password or an
#   empty database name yields a Sync Gateway that either refuses to start or
#   — worse — starts and serves the wrong thing. This script fails loudly
#   where the cause is obvious rather than three layers down in a test run.
#
# USAGE:
#   ./scripts/render_sync_gateway_config.sh
#   (runnable from any working directory; the repo root is resolved from the
#    script's own location)
#
# ARGUMENTS:
#   none
#
# PREREQUISITES:
#   - `.env` at the repo root, populated from `.env.example`. Required keys:
#       SYNC_GATEWAY_DB, SYNC_GATEWAY_CB_USER, SYNC_GATEWAY_CB_PASSWORD
#   - `envsubst` on PATH (GNU gettext; `brew install gettext` on macOS).
#
# EXIT CODES:
#   0  config rendered successfully
#   1  .env missing, envsubst missing, template missing, a referenced variable
#      unset/empty in .env, or a residual ${VARIABLE} in the rendered output
# =============================================================================

# Resolve the repo root from this script's own location so the script works
# from any cwd (scripts/ lives directly under the repo root).
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

ENV_FILE="${REPO_ROOT}/.env"
TEMPLATE="${REPO_ROOT}/sync_gateway/sync_gateway.json.template"
OUTPUT="${REPO_ROOT}/sync_gateway/sync_gateway.json"

if ! command -v envsubst >/dev/null 2>&1; then
  echo "[render-sg] ERROR: envsubst not found on PATH." >&2
  echo "[render-sg]   macOS: brew install gettext && brew link --force gettext" >&2
  echo "[render-sg]   Debian/Ubuntu: apt-get install gettext-base" >&2
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "[render-sg] ERROR: ${ENV_FILE} not found." >&2
  echo "[render-sg]   Copy .env.example to .env and fill in the harness values." >&2
  exit 1
fi

if [ ! -f "$TEMPLATE" ]; then
  echo "[render-sg] ERROR: ${TEMPLATE} not found." >&2
  exit 1
fi

# --- 1. Load .env ------------------------------------------------------------
# Parsed line by line rather than sourced: .env values legitimately contain
# characters the shell would interpret (`<placeholder>` redirects, `&`, `;`),
# and sourcing them would execute rather than assign.
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in
    ''|'#'*) continue ;;
  esac
  case "$line" in
    *=*) ;;
    *) continue ;;
  esac
  key="${line%%=*}"
  value="${line#*=}"
  key="${key#export }"
  # Trim surrounding whitespace on the key only; values are taken verbatim.
  key="$(printf '%s' "$key" | tr -d '[:space:]')"
  [ -z "$key" ] && continue
  export "$key=$value"
done < "$ENV_FILE"

# Mirrors opserver's environment.sh: gives the template an escape hatch for a
# literal `$` that must survive envsubst. The production sync function
# contains no `$` today, but a future edit might.
export DOLLAR='$'

# --- 2. Require every variable the template references ------------------------
# envsubst substitutes an unset variable with "" and exits 0, so the only place
# a missing key can be caught is here, before rendering.
missing=""
while IFS= read -r var; do
  [ -z "$var" ] && continue
  if [ -z "${!var:-}" ]; then
    missing="${missing} ${var}"
  fi
done <<EOF
$(grep -o '\${[A-Za-z_][A-Za-z0-9_]*}' "$TEMPLATE" | tr -d '${}' | sort -u)
EOF

if [ -n "$missing" ]; then
  echo "[render-sg] ERROR: variables referenced by the template are unset or empty in ${ENV_FILE}:" >&2
  for var in $missing; do
    echo "[render-sg]   ${var}" >&2
  done
  echo "[render-sg]   See .env.example for what each one is for." >&2
  exit 1
fi

# --- 3. Render ---------------------------------------------------------------
# Strip whole-line `//` comments first. Sync Gateway 2.8 parses its config with
# Go's encoding/json, which rejects comments outright:
#   [ERR] Error reading config file ...: invalid character '/' looking for
#   beginning of value -- rest.ServerMain() at config.go:1206
# The template keeps its documentation header anyway — the provenance of every
# production-matched value is worth more in the tracked file than in a commit
# message — so the comments are removed here on the way out. Only lines whose
# first non-whitespace characters are `//` are stripped, so the `//` inside
# "http://couchbase:8091" survives.
sed 's,^[[:space:]]*//.*$,,' "$TEMPLATE" | envsubst > "$OUTPUT"

# --- 4. Assert nothing survived unsubstituted --------------------------------
# Belt-and-braces against a template using a form envsubst does not handle
# (e.g. `$VAR` without braces inside a construct, or a nested expansion).
if grep -q '\${' "$OUTPUT"; then
  echo "[render-sg] ERROR: rendered config still contains unsubstituted variables:" >&2
  grep -o '\${[A-Za-z_][A-Za-z0-9_]*}' "$OUTPUT" | sort -u | sed 's/^/[render-sg]   /' >&2
  rm -f "$OUTPUT"
  exit 1
fi

echo "[render-sg] rendered ${TEMPLATE#"${REPO_ROOT}/"} -> ${OUTPUT#"${REPO_ROOT}/"}"
