#!/usr/bin/env bash
# Drop container traffic to the link-local range, which includes the cloud metadata service
# (169.254.169.254). Without this, code running in a container (or an SSRF in the API) could ask
# the instance metadata for credentials, exposing the instance principal used for backups.
# DOCKER-USER is the chain Docker evaluates before its own rules for forwarded (container)
# traffic, and the chain Docker documents for user rules.
#
# Persistence: stockeye-docker-user.service (installed by setup-vm.sh) runs this after
# docker.service on every boot, and is PartOf docker.service, so a Docker restart re-runs it too.
# It is idempotent and never saves Docker's chains into /etc/iptables.
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin

# dockerd creates DOCKER-USER shortly after it starts; wait for it.
for _ in $(seq 1 30); do
  iptables -w -n -L DOCKER-USER >/dev/null 2>&1 && break
  sleep 1
done
iptables -w -n -L DOCKER-USER >/dev/null 2>&1 || { echo "DOCKER-USER chain not found" >&2; exit 1; }

if ! iptables -w -C DOCKER-USER -d 169.254.0.0/16 -j DROP 2>/dev/null; then
  iptables -w -I DOCKER-USER 1 -d 169.254.0.0/16 -j DROP
fi
