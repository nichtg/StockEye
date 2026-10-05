#!/usr/bin/env bash
# Nightly MongoDB backup (run by stockeye-backup.timer as root; installed at
# /usr/local/sbin/stockeye-backup). Dumps the stockeye database, keeps the last N copies locally
# and uploads each to a private OCI Object Storage bucket using the VM's instance principal,
# so no API key or credential file lives on the VM.
set -euo pipefail
umask 077
export PATH=/usr/sbin:/usr/bin:/sbin:/bin

# shellcheck source=deploy/lib.sh
. /usr/local/lib/stockeye/lib.sh
readonly BACKUP_DIR=/var/backups/stockeye
readonly MARKER=/var/lib/stockeye/BACKUP_FAILED
readonly OCI=/opt/oci-cli/bin/oci
readonly KEEP="${BACKUP_KEEP:-7}"
blog() { log stockeye-backup "$@"; }
die() {
  blog "ERROR: $*"
  exit 1
}

namespace="$(env_get OCI_NAMESPACE)"
bucket="$(env_get OCI_BACKUP_BUCKET)"
[[ "$namespace" =~ ^[A-Za-z0-9._-]+$ && "$bucket" =~ ^[A-Za-z0-9._-]+$ ]] \
  || die "OCI_NAMESPACE / OCI_BACKUP_BUCKET missing in $ENV_FILE"
[[ "$KEEP" =~ ^[0-9]+$ && "$KEEP" -ge 1 ]] || die "BACKUP_KEEP must be a positive integer"

install -d -m 0700 "$BACKUP_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
name="stockeye-${stamp}.archive.gz"
tmp="$BACKUP_DIR/.${name}.part"
trap 'rm -f "$tmp"' EXIT

# The password never appears on a command line (host or container): printf is a shell builtin,
# so it goes from the container's own environment into a 0600 temp config file that mongodump
# reads with --config, and the file is deleted on exit.
"$COMPOSE" exec -T mongo sh -c '
  umask 077
  cfg="$(mktemp)"
  trap "rm -f \"$cfg\"" EXIT
  printf "password: %s\n" "$MONGO_INITDB_ROOT_PASSWORD" >"$cfg"
  mongodump --quiet --config="$cfg" --username "$MONGO_INITDB_ROOT_USERNAME" \
    --authenticationDatabase admin --db stockeye --archive --gzip
' >"$tmp" || die "mongodump failed"

[[ -s "$tmp" ]] || die "dump is empty"
gzip -t "$tmp" || die "dump failed gzip integrity check"
mv -f "$tmp" "$BACKUP_DIR/$name"
blog "dumped $name ($(stat -c %s "$BACKUP_DIR/$name") bytes)"

"$OCI" os object put --auth instance_principal --namespace-name "$namespace" \
  --bucket-name "$bucket" --name "$name" --file "$BACKUP_DIR/$name" --no-multipart --force >/dev/null \
  || die "upload to bucket $bucket failed (local copy kept)"
blog "uploaded $name to bucket $bucket"
rm -f "$MARKER"

# Keep the newest $KEEP local copies.
mapfile -t old < <(find "$BACKUP_DIR" -maxdepth 1 -name 'stockeye-*.archive.gz' -printf '%f\n' | sort -r | tail -n +"$((KEEP + 1))")
for f in "${old[@]}"; do
  rm -f -- "${BACKUP_DIR:?}/$f"
  blog "pruned local $f"
done
