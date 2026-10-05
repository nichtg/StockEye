#!/usr/bin/env bash
# Forced command for the `deploy` SSH user. Installed root-owned at /usr/local/sbin/stockeye-deploy
# and reached as: authorized_keys command="/usr/bin/sudo /usr/local/sbin/stockeye-deploy",restrict
#
# Why sudo: the deploy user has no docker rights (docker group == root). The sudoers rule allows
# exactly this one script with NO arguments, and keeps only SSH_ORIGINAL_COMMAND in the
# environment, so the only input the CI key controls is one validated string: an image digest.
set -euo pipefail
umask 077
export PATH=/usr/sbin:/usr/bin:/sbin:/bin

# shellcheck source=deploy/lib.sh
. /usr/local/lib/stockeye/lib.sh
readonly LOCK_FILE=/run/stockeye-deploy.lock
readonly HEALTH_TIMEOUT_S=180
dlog() { log stockeye-deploy "$@"; }
die() {
  dlog "ERROR: $*"
  exit 1
}

# 1. Input: exactly one sha256 digest, nothing else.
digest="${SSH_ORIGINAL_COMMAND:-}"
if ! [[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  dlog "rejected: SSH_ORIGINAL_COMMAND is not a sha256 digest"
  exit 1
fi

# 2. The image repository comes from the root-owned env file, never from the caller.
repo="$(env_get GHCR_IMAGE)"
[[ "$repo" =~ ^ghcr\.io/[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._/-]*$ ]] || die "GHCR_IMAGE missing or malformed in $ENV_FILE"
# Only non-comment lines count: the template's own comments mention the placeholder.
! grep -q '^[^#]*CHANGE_ME' "$ENV_FILE" || die "$ENV_FILE still has CHANGE_ME placeholders"

exec 9>"$LOCK_FILE"
flock -n 9 || die "another deploy is running"

new="${repo}@${digest}"
previous="$(sed -n 's/^API_IMAGE=//p' "$STATE_FILE" 2>/dev/null | head -n 1 || true)"
dlog "deploying $new (previous: ${previous:-none})"

write_state() {
  local tmp
  tmp="$(mktemp /etc/stockeye/.state.XXXXXX)"
  printf 'API_IMAGE=%s\n' "$1" >"$tmp"
  chmod 0600 "$tmp"
  mv -f "$tmp" "$STATE_FILE"
}

# "Healthy" is defined once, by the api HEALTHCHECK in backend/Dockerfile: HTTP 200 from
# /api/health AND database == "ok". The gate just waits for Docker to report it.
wait_healthy() {
  local deadline=$((SECONDS + HEALTH_TIMEOUT_S)) cid status
  while ((SECONDS < deadline)); do
    cid="$("$COMPOSE" ps -q api 2>/dev/null || true)"
    if [[ -n "$cid" ]]; then
      status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cid" 2>/dev/null || true)"
      [[ "$status" == healthy ]] && return 0
    fi
    sleep 3
  done
  return 1
}

# Keep the images of the current and previous digest; remove every other image of this repo.
prune_images() {
  local keep_a=$1 keep_b=${2:-} ref id
  while read -r ref id; do
    [[ "$ref" == "$keep_a" || "$ref" == "$keep_b" ]] && continue
    docker rmi "$id" >/dev/null 2>&1 || true
  done < <(docker image ls "$repo" --digests --no-trunc --format '{{.Repository}}@{{.Digest}} {{.ID}}')
}

# 3. Pull first: a bad digest fails here without touching the running stack.
docker pull --quiet "$new" >/dev/null || die "docker pull failed for $new"

# 4. Switch. `up -d` (all services) is idempotent: unchanged caddy/mongo are left alone, and the
#    very first deploy also brings them up.
write_state "$new"
if "$COMPOSE" up -d --remove-orphans && wait_healthy; then
  dlog "deploy ok: $new"
  prune_images "$new" "$previous"
  exit 0
fi

# 5. Roll back to the previous digest.
dlog "new image unhealthy; rolling back"
if [[ -n "$previous" ]]; then
  write_state "$previous"
  "$COMPOSE" up -d --remove-orphans || true
  if wait_healthy; then
    dlog "rolled back to $previous"
  else
    dlog "ERROR: rollback to $previous is also unhealthy"
  fi
else
  dlog "no previous image to roll back to"
fi
exit 1
