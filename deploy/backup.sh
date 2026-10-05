#!/usr/bin/env bash
# Nightly MongoDB backup (run by stockeye-backup.timer as root; installed at
# /usr/local/sbin/stockeye-backup). Dumps the stockeye database, keeps the last N copies locally
# and uploads each to a private OCI Object Storage bucket using the VM's instance principal,
# so no API key or credential file lives on the VM.
set -euo pipefail
umask 077
export PATH=/usr/sbin:/usr/bin:/sbin:/bin

readonly ENV_FILE=/etc/stockeye/stockeye.env
readonly STATE_FILE=/etc/stockeye/state.env
readonly COMPOSE_FILE=/opt/stockeye/compose.yml
readonly BACKUP_DIR=/var/backups/stockeye
readonly OCI=/opt/oci-cli/bin/oci
readonly KEEP="${BACKUP_KEEP:-7}"

log() { logger -t stockeye-backup -- "$*" || true; echo "stockeye-backup: $*" >&2; }
die() { log "ERROR: $*"; exit 1; }
getenv() { sed -n "s/^$1=//p" "$ENV_FILE" | head -n 1; }

namespace="$(getenv OCI_NAMESPACE)"
bucket="$(getenv OCI_BACKUP_BUCKET)"
[[ "$namespace" =~ ^[A-Za-z0-9._-]+$ && "$bucket" =~ ^[A-Za-z0-9._-]+$ ]] \
  || die "OCI_NAMESPACE / OCI_BACKUP_BUCKET missing in $ENV_FILE"
[[ "$KEEP" =~ ^[0-9]+$ && "$KEEP" -ge 1 ]] || die "BACKUP_KEEP must be a positive integer"

install -d -m 0700 "$BACKUP_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
name="stockeye-${stamp}.archive.gz"
tmp="$BACKUP_DIR/.${name}.part"
trap 'rm -f "$tmp"' EXIT

# Credentials are read from the container's own environment, so they never appear on the host.
docker compose --project-name stockeye --env-file "$ENV_FILE" --env-file "$STATE_FILE" \
  -f "$COMPOSE_FILE" exec -T mongo sh -c \
  'exec mongodump --quiet --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --db stockeye --archive --gzip' \
  >"$tmp" || die "mongodump failed"

[[ -s "$tmp" ]] || die "dump is empty"
gzip -t "$tmp" || die "dump failed gzip integrity check"
mv -f "$tmp" "$BACKUP_DIR/$name"
log "dumped $name ($(stat -c %s "$BACKUP_DIR/$name") bytes)"

"$OCI" os object put --auth instance_principal --namespace-name "$namespace" \
  --bucket-name "$bucket" --name "$name" --file "$BACKUP_DIR/$name" --no-multipart --force >/dev/null \
  || die "upload to bucket $bucket failed (local copy kept)"
log "uploaded $name to bucket $bucket"

# Keep the newest $KEEP local copies.
mapfile -t old < <(find "$BACKUP_DIR" -maxdepth 1 -name 'stockeye-*.archive.gz' -printf '%f\n' | sort -r | tail -n +"$((KEEP + 1))")
for f in "${old[@]}"; do
  rm -f -- "${BACKUP_DIR:?}/$f"
  log "pruned local $f"
done
