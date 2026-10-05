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

readonly ENV_FILE=/etc/stockeye/stockeye.env
readonly STATE_FILE=/etc/stockeye/state.env
readonly COMPOSE_FILE=/opt/stockeye/compose.yml
readonly LOCK_FILE=/run/stockeye-deploy.lock
readonly HEALTH_TIMEOUT_S=180

log() { logger -t stockeye-deploy -- "$*" || true; echo "stockeye-deploy: $*" >&2; }
die() { log "ERROR: $*"; exit 1; }

compose() {
  docker compose --project-name stockeye --env-file "$ENV_FILE" --env-file "$STATE_FILE" \
    -f "$COMPOSE_FILE" "$@"
}

# 1. Input: exactly one sha256 digest, nothing else.
digest="${SSH_ORIGINAL_COMMAND:-}"
if ! [[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  log "rejected: SSH_ORIGINAL_COMMAND is not a sha256 digest"
  exit 1
fi

# 2. Image repository comes from the root-owned env file, never from the caller.
repo="$(sed -n 's/^GHCR_IMAGE=//p' "$ENV_FILE" | head -n 1)"
[[ "$repo" =~ ^ghcr\.io/[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._/-]*$ ]] || die "GHCR_IMAGE missing or malformed in $ENV_FILE"
! grep -q 'CHANGE_ME' "$ENV_FILE" || die "$ENV_FILE still has CHANGE_ME placeholders"

exec 9>"$LOCK_FILE"
flock -n 9 || die "another deploy is running"

new="${repo}@${digest}"
previous="$(sed -n 's/^API_IMAGE=//p' "$STATE_FILE" 2>/dev/null | head -n 1 || true)"
log "deploying $new (previous: ${previous:-none})"

write_state() {
  local tmp
  tmp="$(mktemp /etc/stockeye/.state.XXXXXX)"
  printf 'API_IMAGE=%s\n' "$1" >"$tmp"
  chmod 0600 "$tmp"
  mv -f "$tmp" "$STATE_FILE"
}

wait_healthy() {
  local deadline=$((SECONDS + HEALTH_TIMEOUT_S)) cid status
  while ((SECONDS < deadline)); do
    cid="$(compose ps -q api 2>/dev/null || true)"
    if [[ -n "$cid" ]]; then
      status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cid" 2>/dev/null || true)"
      [[ "$status" == healthy ]] && return 0
    fi
    sleep 3
  done
  return 1
}

# 3. Pull first: a bad digest fails here without touching the running stack.
docker pull --quiet "$new" >/dev/null || die "docker pull failed for $new"

# 4. Switch. `up -d` (all services) is idempotent: unchanged caddy/mongo are left alone, and the
#    very first deploy also brings them up.
write_state "$new"
if compose up -d --remove-orphans && wait_healthy; then
  log "deploy ok: $new"
  exit 0
fi

# 5. Roll back to the previous digest.
log "new image unhealthy; rolling back"
if [[ -n "$previous" ]]; then
  write_state "$previous"
  compose up -d --remove-orphans || true
  if wait_healthy; then
    log "rolled back to $previous"
  else
    log "ERROR: rollback to $previous is also unhealthy"
  fi
else
  log "no previous image to roll back to"
fi
exit 1
