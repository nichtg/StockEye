#!/usr/bin/env bash
# One-time (and safely re-runnable) setup of the Oracle Always Free Ubuntu VM.
# Run as root from a checkout of this repo's deploy/ directory:
#
#   sudo ADMIN_PUBKEY='ssh-ed25519 AAAA... you@laptop' \
#        DEPLOY_PUBKEY='ssh-ed25519 AAAA... github-deploy' \
#        ./deploy/setup-vm.sh
#
# READ IT FIRST. It changes sshd, the firewall and sudo rules. Keep your current SSH session
# open and confirm you can log in as `admin` in a second terminal before closing it.
set -euo pipefail
umask 022
export DEBIAN_FRONTEND=noninteractive

[[ $EUID -eq 0 ]] || { echo "run as root (sudo)"; exit 1; }
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${ADMIN_PUBKEY:?set ADMIN_PUBKEY to your ssh-ed25519 public key line}"
: "${DEPLOY_PUBKEY:?set DEPLOY_PUBKEY to the CI deploy key ssh-ed25519 public key line}"
# The comment field is restricted so it cannot break out of the authorized_keys options below.
key_re='^ssh-ed25519 [A-Za-z0-9+/=]+( [A-Za-z0-9@._-]+)?$'
[[ "$ADMIN_PUBKEY" =~ $key_re ]] || { echo "ADMIN_PUBKEY must be a single ssh-ed25519 line"; exit 1; }
[[ "$DEPLOY_PUBKEY" =~ $key_re ]] || { echo "DEPLOY_PUBKEY must be a single ssh-ed25519 line"; exit 1; }
for f in compose.yml Caddyfile mongo-init.sh deploy.sh backup.sh; do
  [[ -f "$SRC/$f" ]] || { echo "missing $SRC/$f"; exit 1; }
done

step() { printf '\n== %s\n' "$*"; }

step "Base packages"
apt-get update -qq
apt-get install -y -qq unattended-upgrades ca-certificates curl gnupg iptables-persistent \
  python3-venv sudo openssh-server

step "Unattended upgrades with a nightly reboot window"
cat >/etc/apt/apt.conf.d/20auto-upgrades <<'CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
CONF
cat >/etc/apt/apt.conf.d/52stockeye-unattended <<'CONF'
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-WithUsers "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
CONF

step "Users: admin (your key, sudo) and deploy (forced command only)"
id admin >/dev/null 2>&1 || useradd --create-home --shell /bin/bash admin
install -d -m 700 -o admin -g admin /home/admin/.ssh
printf '%s\n' "$ADMIN_PUBKEY" >/home/admin/.ssh/authorized_keys
chown admin:admin /home/admin/.ssh/authorized_keys
chmod 600 /home/admin/.ssh/authorized_keys
# A key-only account has no password, so sudo must not ask for one. Accepted: the admin key is root.
echo 'admin ALL=(ALL) NOPASSWD:ALL' >/etc/sudoers.d/90-stockeye-admin
chmod 440 /etc/sudoers.d/90-stockeye-admin

id deploy >/dev/null 2>&1 || useradd --create-home --shell /bin/bash deploy
# Root-owned home and authorized_keys: the deploy user cannot rewrite its own forced command.
chown root:root /home/deploy
chmod 755 /home/deploy
install -d -m 755 -o root -g root /home/deploy/.ssh
printf 'command="/usr/bin/sudo /usr/local/sbin/stockeye-deploy",restrict %s\n' "$DEPLOY_PUBKEY" \
  >/home/deploy/.ssh/authorized_keys
chown root:root /home/deploy/.ssh/authorized_keys
chmod 644 /home/deploy/.ssh/authorized_keys
# The narrowest sudo rule: this one script, no arguments (the trailing ""), and only
# SSH_ORIGINAL_COMMAND survives into it. A group-based setup would need docker-group access,
# which is root-equivalent, so sudo-on-one-script is the smaller grant.
cat >/etc/sudoers.d/91-stockeye-deploy <<'CONF'
Defaults!/usr/local/sbin/stockeye-deploy env_reset, env_keep="SSH_ORIGINAL_COMMAND"
deploy ALL=(root) NOPASSWD: /usr/local/sbin/stockeye-deploy ""
CONF
chmod 440 /etc/sudoers.d/91-stockeye-deploy
visudo -cf /etc/sudoers.d/90-stockeye-admin >/dev/null
visudo -cf /etc/sudoers.d/91-stockeye-deploy >/dev/null

step "sshd: key-only, no root login"
cat >/etc/ssh/sshd_config.d/10-stockeye.conf <<'CONF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
X11Forwarding no
Match User deploy
    AllowTcpForwarding no
    AllowAgentForwarding no
    PermitTTY no
CONF
if sshd -t; then
  systemctl reload ssh
else
  rm -f /etc/ssh/sshd_config.d/10-stockeye.conf
  echo "sshd config test failed; hardening drop-in removed"
  exit 1
fi

step "Firewall: allow 22/80/443 persistently (Oracle's Ubuntu image rejects the rest)"
if ! iptables -C INPUT -p tcp -m multiport --dports 22,80,443 -m conntrack --ctstate NEW -j ACCEPT 2>/dev/null; then
  iptables -I INPUT 1 -p tcp -m multiport --dports 22,80,443 -m conntrack --ctstate NEW -j ACCEPT
fi
netfilter-persistent save

step "Docker Engine + compose plugin (Docker's apt repo, key fingerprint checked)"
if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  fpr="$(gpg --show-keys --with-colons /etc/apt/keyrings/docker.asc | awk -F: '$1=="fpr"{print $10; exit}')"
  [[ "$fpr" == 9DC858229FC7DD38854AE2D88D81803C0EBFCD88 ]] || { echo "Docker key fingerprint mismatch: $fpr"; exit 1; }
  # shellcheck source=/dev/null
  . /etc/os-release
  arch="$(dpkg --print-architecture)"
  cat >/etc/apt/sources.list.d/docker.sources <<CONF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${VERSION_CODENAME}
Components: stable
Architectures: ${arch}
Signed-By: /etc/apt/keyrings/docker.asc
CONF
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker

step "Stack files and secrets directory"
install -d -m 755 /opt/stockeye
install -m 644 "$SRC/compose.yml" /opt/stockeye/compose.yml
install -m 644 "$SRC/Caddyfile" /opt/stockeye/Caddyfile
install -m 755 "$SRC/mongo-init.sh" /opt/stockeye/mongo-init.sh
install -d -m 700 -o root -g root /etc/stockeye
if [[ ! -f /etc/stockeye/stockeye.env ]]; then
  cat >/etc/stockeye/stockeye.env <<'CONF'
# StockEye production settings and secrets. root:root 0600. Never commit or paste this file.
# Replace every CHANGE_ME (deploy.sh refuses to run while any remain). No spaces around "=".
# Generate each secret on the VM itself.

# The reserved public IP of this VM (also the address Caddy gets a certificate for).
PUBLIC_IP=CHANGE_ME
# Image repository, all lowercase: ghcr.io/<github-org>/stockeye-api
GHCR_IMAGE=CHANGE_ME

# MongoDB root account (used only by Mongo itself and the backup script).
MONGO_ROOT_USERNAME=stockeye_root
# generate: openssl rand -hex 24
MONGO_ROOT_PASSWORD=CHANGE_ME
# The API's own account, readWrite on the stockeye database only.
MONGO_APP_USERNAME=stockeye_app
# generate: openssl rand -hex 24   (hex only: it is embedded in a URI and a JS string)
MONGO_APP_PASSWORD=CHANGE_ME
# Mongo creates both accounts only when its data volume is first created. To change a
# password later, see "Rotating secrets" in docs/DEPLOY.md.

# Signs access tokens. generate: openssl rand -hex 32
# (or: python3 -c "import secrets; print(secrets.token_urlsafe(48))")
STOCKEYE_JWT_SECRET=CHANGE_ME
# The Pages origin: scheme + host only, no path, no trailing slash. A JSON list; keep the single quotes.
STOCKEYE_CORS_ORIGINS='["https://CHANGE_ME.github.io"]'

# Market-data keys (leave empty to disable a provider). Copy them from the providers' dashboards.
STOCKEYE_FINNHUB_API_KEY=
STOCKEYE_MARKETAUX_API_KEY=
STOCKEYE_ALPHAVANTAGE_API_KEY=

# Backups: your Object Storage namespace (Console > Tenancy details) and the private bucket name.
OCI_NAMESPACE=CHANGE_ME
OCI_BACKUP_BUCKET=CHANGE_ME
CONF
fi
chown root:root /etc/stockeye/stockeye.env
chmod 600 /etc/stockeye/stockeye.env
[[ -f /etc/stockeye/state.env ]] || : >/etc/stockeye/state.env
chown root:root /etc/stockeye/state.env
chmod 600 /etc/stockeye/state.env

step "Deploy, backup and compose-wrapper scripts (root-owned)"
install -m 755 -o root -g root "$SRC/deploy.sh" /usr/local/sbin/stockeye-deploy
install -m 755 -o root -g root "$SRC/backup.sh" /usr/local/sbin/stockeye-backup
cat >/usr/local/sbin/stockeye-compose <<'CONF'
#!/bin/sh
# docker compose for the production stack, with the right project and env files.
exec docker compose --project-name stockeye --env-file /etc/stockeye/stockeye.env \
  --env-file /etc/stockeye/state.env -f /opt/stockeye/compose.yml "$@"
CONF
chmod 755 /usr/local/sbin/stockeye-compose

step "OCI CLI (for backups; authenticates as the instance, no key file)"
if [[ ! -x /opt/oci-cli/bin/oci ]]; then
  python3 -m venv /opt/oci-cli
  /opt/oci-cli/bin/pip install --quiet "oci-cli==3.94.1"
fi

step "Nightly backup timer (02:30 UTC)"
cat >/etc/systemd/system/stockeye-backup.service <<'CONF'
[Unit]
Description=StockEye MongoDB backup to OCI Object Storage
After=docker.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/stockeye-backup
CONF
cat >/etc/systemd/system/stockeye-backup.timer <<'CONF'
[Unit]
Description=Nightly StockEye backup

[Timer]
OnCalendar=*-*-* 02:30:00 UTC
RandomizedDelaySec=600
Persistent=true

[Install]
WantedBy=timers.target
CONF
systemctl daemon-reload
systemctl enable --now stockeye-backup.timer

step "Done"
host_fpr="$(ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub)"
host_key="$(cut -d' ' -f1,2 /etc/ssh/ssh_host_ed25519_key.pub)"
cat <<MSG

SSH host key fingerprint (ed25519). Compare it with what you pin in GitHub:
${host_fpr}

known_hosts line for the GitHub variable DEPLOY_KNOWN_HOSTS (replace <PUBLIC_IP>):
<PUBLIC_IP> ${host_key}

Next: edit /etc/stockeye/stockeye.env, then run the "backend-image" workflow to deploy.
MSG
