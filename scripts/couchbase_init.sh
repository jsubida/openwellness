#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# couchbase_init.sh
#
# DESCRIPTION:
#   Idempotent one-shot provisioner for the LOCAL integration-test Couchbase
#   Server 6.6 Community Edition node defined in docker-compose.yml. Run as the
#   entrypoint of the `couchbase-init` service, which starts only after the
#   `couchbase` service reports healthy and which the `sync-gateway` service
#   waits on via `service_completed_successfully`.
#
#   It initializes the cluster, creates the single bucket `spring`, and upserts
#   the Couchbase RBAC user Sync Gateway authenticates as, then exits 0.
#
#   BUCKET AND USER NAMES ARE PRODUCTION VALUES, NOT DEFAULTS. Production runs
#   a single bucket named `spring` and Sync Gateway authenticates as `sgw`
#   (opserver `.planning/todos/pending/verify-production-datastore-topology.md`).
#   The harness exists to reproduce production Sync Gateway behavior, so these
#   names must not be "tidied". Note this differs from opserver's analogous
#   dev-Couchbase script, which provisions a differently-named bucket for the
#   legacy app tier — that script was the pattern, not the source of values.
#
#   Every step is guarded so the stack can be brought up repeatedly across test
#   runs without erroring under `set -e`, and every step logs what it did or
#   why it skipped so a failed bring-up is diagnosable from
#   `docker compose logs couchbase-init`.
#
# USAGE:
#   docker compose up -d couchbase couchbase-init sync-gateway
#   (or directly: bash scripts/couchbase_init.sh, from inside a container that
#    can reach COUCHBASE_HOST and has couchbase-cli on PATH)
#
# ENVIRONMENT VARIABLES (with defaults):
#   COUCHBASE_HOST            Couchbase REST host:port  (default: couchbase:8091)
#   COUCHBASE_ADMIN_USER      Cluster admin username    (default: Administrator)
#   COUCHBASE_ADMIN_PASSWORD  Cluster admin password    (default: password)
#   SYNC_GATEWAY_CB_USER      Couchbase user SG uses    (default: sgw)
#   SYNC_GATEWAY_CB_PASSWORD  Password for that user    (default: password)
#
# PREREQUISITES:
#   - Runs inside the couchbase:community-6.6.0 image (ships bash, curl and
#     couchbase-cli on PATH).
#   - The `couchbase` service must be reachable at COUCHBASE_HOST.
#
# EXIT CODES:
#   0  provisioning complete (or already provisioned)
#   1  Couchbase REST API never became reachable within the wait budget, or a
#      provisioning step failed
# =============================================================================

HOST="${COUCHBASE_HOST:-couchbase:8091}"
ADMIN="${COUCHBASE_ADMIN_USER:-Administrator}"
ADMINPW="${COUCHBASE_ADMIN_PASSWORD:-password}"
# Fixed by production, not configurable: one bucket, named `spring`.
BUCKET="spring"
SGUSER="${SYNC_GATEWAY_CB_USER:-sgw}"
SGPASS="${SYNC_GATEWAY_CB_PASSWORD:-password}"

# --- 1. Wait for the Couchbase REST API to answer -----------------------------
echo "[couchbase-init] waiting for Couchbase REST API at http://$HOST/pools ..."
tries=0
until curl -s -o /dev/null "http://$HOST/pools" 2>/dev/null; do
  tries=$((tries + 1))
  if [ "$tries" -ge 60 ]; then
    echo "[couchbase-init] ERROR: Couchbase REST API at $HOST not reachable after $tries tries" >&2
    exit 1
  fi
  sleep 3
done
echo "[couchbase-init] Couchbase REST API is up."

# --- 2. cluster-init (guarded) ------------------------------------------------
# Before init, /pools/default returns 404 to an authenticated request; after
# init it returns 200. That is the unambiguous "is this cluster provisioned"
# signal — container liveness is not.
if curl -sf -u "$ADMIN:$ADMINPW" "http://$HOST/pools/default" >/dev/null 2>&1; then
  echo "[couchbase-init] cluster already initialized — skipping cluster-init."
else
  echo "[couchbase-init] initializing cluster (services data,index,query; 512/256 MB) ..."
  couchbase-cli cluster-init -c "$HOST" \
    --cluster-username "$ADMIN" \
    --cluster-password "$ADMINPW" \
    --services data,index,query \
    --cluster-ramsize 512 \
    --cluster-index-ramsize 256
  echo "[couchbase-init] cluster initialized."
fi

# --- 3. bucket-create (guarded) -----------------------------------------------
if curl -sf -u "$ADMIN:$ADMINPW" "http://$HOST/pools/default/buckets/$BUCKET" >/dev/null 2>&1; then
  echo "[couchbase-init] bucket '$BUCKET' already exists — skipping bucket-create."
else
  echo "[couchbase-init] creating bucket '$BUCKET' (couchbase-type, 256 MB, 0 replicas) ..."
  couchbase-cli bucket-create -c "$HOST" -u "$ADMIN" -p "$ADMINPW" \
    --bucket "$BUCKET" \
    --bucket-type couchbase \
    --bucket-ramsize 256 \
    --bucket-replica 0 \
    --wait
  echo "[couchbase-init] bucket '$BUCKET' created."
fi

# --- 4. Sync Gateway's Couchbase user (idempotent — --set creates or edits) ---
# bucket_full_access ("Application Access") is the ONLY bucket-scoped role
# Couchbase Server 6.6 Community Edition offers. Confirmed empirically against
# this exact image: GET /settings/rbac/roles returns admin, ro_admin and
# bucket_full_access — nothing else. The fine-grained query_* and
# query_manage_index roles are Enterprise-only, so asking for them here fails
# the whole user-manage call with "roles are unknown, malformed or role
# parameters are undefined". It also means production's `sgw` user necessarily
# holds this same coarse role, which is worth knowing: on CE there is no
# least-privilege split available for Sync Gateway.
echo "[couchbase-init] upserting Couchbase user '$SGUSER' for Sync Gateway on bucket '$BUCKET' ..."
couchbase-cli user-manage -c "$HOST" -u "$ADMIN" -p "$ADMINPW" \
  --set \
  --rbac-username "$SGUSER" \
  --rbac-password "$SGPASS" \
  --rbac-name "$SGUSER" \
  --roles "bucket_full_access[$BUCKET]" \
  --auth-domain local
echo "[couchbase-init] user '$SGUSER' present."

echo "[couchbase-init] provisioning complete: cluster ready, bucket '$BUCKET' and user '$SGUSER' present."
