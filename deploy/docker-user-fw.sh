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

# On Oracle the VCN DNS resolver is also 169.254.169.254 (port 53), and Docker's embedded DNS
# forwards to it from inside the container's namespace, so DNS must stay open ahead of the DROP.
# Rules are removed then re-inserted in a fixed order, which keeps re-runs idempotent.
rules=(
  "-d 169.254.169.254/32 -p udp --dport 53 -j RETURN"
  "-d 169.254.169.254/32 -p tcp --dport 53 -j RETURN"
  "-d 169.254.0.0/16 -j DROP"
)
for rule in "${rules[@]}"; do
  # shellcheck disable=SC2086  # each rule is a list of iptables words
  while iptables -w -D DOCKER-USER $rule 2>/dev/null; do :; done
done
position=1
for rule in "${rules[@]}"; do
  # shellcheck disable=SC2086
  iptables -w -I DOCKER-USER "$position" $rule
  position=$((position + 1))
done
