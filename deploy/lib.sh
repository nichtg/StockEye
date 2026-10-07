# Shared helpers for stockeye-deploy and stockeye-backup (installed root-owned at
# /usr/local/lib/stockeye/lib.sh and sourced). Must not run anything on load.

ENV_FILE=/etc/stockeye/stockeye.env
STATE_FILE=/etc/stockeye/state.env
# The one place that knows the compose file and env files.
COMPOSE=/usr/local/sbin/stockeye-compose

# log TAG MESSAGE...  -> syslog and stderr
log() {
  local tag=$1
  shift
  logger -t "$tag" -- "$*" || true
  echo "$tag: $*" >&2
}

# env_get KEY -> the value of KEY= from the secrets file (first match, no quote handling).
env_get() { sed -n "s/^$1=//p" "$ENV_FILE" | head -n 1; }
