#!/usr/bin/env bash
# One-time (and safely re-runnable) setup of the Oracle Always Free Ubuntu VM.
# Run as root from a checkout of this repo's deploy/ directory:
#
#   sudo ADMIN_PUBKEY='ssh-ed25519 AAAA... you@laptop' \
#        DEPLOY_PUBKEY='ssh-ed25519 AAAA... github-deploy' \
#        bash ./deploy/setup-vm.sh
#
# READ IT FIRST. It changes sshd, the firewall and sudo rules. It does NOT restrict who may log
# in over SSH or lock the default `ubuntu` user: do that afterwards with harden-ssh.sh, once you
# have confirmed `ssh admin@...` works from a second terminal.
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
for f in compose.yml Caddyfile 10-app-user.js stockeye.env.example lib.sh stockeye-compose.sh \
  deploy.sh backup.sh stockeye-backup-failed.sh docker-user-fw.sh oci-cli.requirements.txt; do
  [[ -f "$SRC/$f" ]] || { echo "missing $SRC/$f"; exit 1; }
done

step() { printf '\n== %s\n' "$*"; }

step "Base packages"
apt-get update -qq
apt-get install -y -qq unattended-upgrades ca-certificates curl gnupg iptables-persistent \
  python3-venv sudo openssh-server

step "Unattended upgrades with a nightly reboot window (Ubuntu and Docker repos)"
cat >/etc/apt/apt.conf.d/20auto-upgrades <<'CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
CONF
# "::" appends to the default origin list instead of replacing it.
cat >/etc/apt/apt.conf.d/52stockeye-unattended <<'CONF'
Unattended-Upgrade::Origins-Pattern:: "origin=Docker,label=Docker CE";
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-WithUsers "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:00";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
CONF

step "Users: admin (your key, sudo) and deploy (forced command only)"
# Ubuntu ships a legacy `admin` group, so a plain `useradd admin` fails with "group admin exists"; reuse it as the
# user's primary group then (sudo comes from the explicit NOPASSWD rule below, not from that group).
if ! id admin >/dev/null 2>&1; then
  if getent group admin >/dev/null; then
    useradd --create-home --shell /bin/bash --gid admin admin
  else
    useradd --create-home --shell /bin/bash admin
  fi
fi
install -d -m 700 -o admin -g admin /home/admin/.ssh
printf '%s\n' "$ADMIN_PUBKEY" >/home/admin/.ssh/authorized_keys
chown admin:admin /home/admin/.ssh/authorized_keys
chmod 600 /home/admin/.ssh/authorized_keys
# A key-only account has no password, so sudo must not ask for one. Accepted: the admin key is root.
echo 'admin ALL=(ALL) NOPASSWD:ALL' >/etc/sudoers.d/90-stockeye-admin
chmod 440 /etc/sudoers.d/90-stockeye-admin

# The deploy account runs only the forced command. /bin/sh is required: sshd runs `command=`
# through the account's shell, so nologin would refuse it. No skel dotfiles, root-owned home and
# authorized_keys: the account cannot rewrite its own forced command or login scripts.
id deploy >/dev/null 2>&1 || useradd --no-create-home --home-dir /home/deploy --shell /bin/sh deploy
usermod --shell /bin/sh deploy
install -d -m 755 -o root -g root /home/deploy /home/deploy/.ssh
find /home/deploy -mindepth 1 -maxdepth 1 ! -name .ssh -exec rm -rf {} +
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
# `restrict` in authorized_keys already removes forwarding and pty for the deploy key.
cat >/etc/ssh/sshd_config.d/10-stockeye.conf <<'CONF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
X11Forwarding no
CONF
if sshd -t; then
  systemctl try-reload-or-restart ssh
else
  rm -f /etc/ssh/sshd_config.d/10-stockeye.conf
  echo "sshd config test failed; hardening drop-in removed"
  exit 1
fi

step "Firewall: allow 22/80/443 in the saved rules and the live rules"
# Only edit the saved file and the live INPUT chain. Never run `netfilter-persistent save`:
# once Docker exists that would also persist Docker's own chains and stale container rules.
RULE='-A INPUT -p tcp -m multiport --dports 22,80,443 -m conntrack --ctstate NEW -j ACCEPT'
rules=/etc/iptables/rules.v4
if [[ -f "$rules" ]] && ! grep -qxF -- "$RULE" "$rules"; then
  # Oracle's image ends INPUT with a catch-all REJECT; the ACCEPT must come before it.
  awk -v rule="$RULE" '!done && /^-A INPUT .*-j REJECT/ { print rule; done = 1 } { print }' "$rules" >"$rules.new"
  grep -qxF -- "$RULE" "$rules.new" || { rm -f "$rules.new"; echo "no INPUT REJECT line in $rules; add the rule by hand"; exit 1; }
  cp -p "$rules" "$rules.bak-stockeye"
  mv "$rules.new" "$rules"
  chmod 640 "$rules"
fi
if ! iptables -C INPUT -p tcp -m multiport --dports 22,80,443 -m conntrack --ctstate NEW -j ACCEPT 2>/dev/null; then
  iptables -I INPUT 1 -p tcp -m multiport --dports 22,80,443 -m conntrack --ctstate NEW -j ACCEPT
fi

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

step "Scripts (root-owned)"
install -d -m 755 -o root -g root /usr/local/lib/stockeye
install -m 644 -o root -g root "$SRC/lib.sh" /usr/local/lib/stockeye/lib.sh
install -m 755 -o root -g root "$SRC/stockeye-compose.sh" /usr/local/sbin/stockeye-compose
install -m 755 -o root -g root "$SRC/deploy.sh" /usr/local/sbin/stockeye-deploy
install -m 755 -o root -g root "$SRC/backup.sh" /usr/local/sbin/stockeye-backup
install -m 755 -o root -g root "$SRC/stockeye-backup-failed.sh" /usr/local/sbin/stockeye-backup-failed
install -m 755 -o root -g root "$SRC/docker-user-fw.sh" /usr/local/sbin/stockeye-docker-user-fw

step "Block containers from the cloud metadata service (DOCKER-USER rule, re-applied on boot)"
cat >/etc/systemd/system/stockeye-docker-user.service <<'CONF'
[Unit]
Description=Drop container traffic to 169.254.0.0/16 (cloud metadata service)
After=docker.service
Requires=docker.service
PartOf=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/sbin/stockeye-docker-user-fw

[Install]
WantedBy=multi-user.target docker.service
CONF
systemctl daemon-reload
systemctl enable stockeye-docker-user.service
systemctl restart stockeye-docker-user.service

step "Stack files and secrets directory"
install -d -m 755 /opt/stockeye
install -m 644 "$SRC/compose.yml" /opt/stockeye/compose.yml
install -m 644 "$SRC/Caddyfile" /opt/stockeye/Caddyfile
install -m 644 "$SRC/10-app-user.js" /opt/stockeye/10-app-user.js
install -d -m 700 -o root -g root /etc/stockeye
[[ -f /etc/stockeye/stockeye.env ]] || install -m 600 -o root -g root "$SRC/stockeye.env.example" /etc/stockeye/stockeye.env
chown root:root /etc/stockeye/stockeye.env
chmod 600 /etc/stockeye/stockeye.env
[[ -f /etc/stockeye/state.env ]] || : >/etc/stockeye/state.env
chown root:root /etc/stockeye/state.env
chmod 600 /etc/stockeye/state.env

step "OCI CLI (for backups; authenticates as the instance, no key file)"
if [[ ! -x /opt/oci-cli/bin/oci ]]; then
  python3 -m venv /opt/oci-cli
  # Every dependency is pinned with hashes (generated for aarch64 / Python 3.12).
  /opt/oci-cli/bin/pip install --quiet --require-hashes --no-deps -r "$SRC/oci-cli.requirements.txt"
fi

step "Nightly backup timer (02:30 UTC) with a loud failure marker"
cat >/etc/systemd/system/stockeye-backup.service <<'CONF'
[Unit]
Description=StockEye MongoDB backup to OCI Object Storage
After=docker.service
OnFailure=stockeye-backup-failed.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/stockeye-backup
CONF
cat >/etc/systemd/system/stockeye-backup-failed.service <<'CONF'
[Unit]
Description=Record that the StockEye backup failed

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/stockeye-backup-failed
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

Next:
  1. From a SECOND terminal confirm: ssh admin@<PUBLIC_IP> 'sudo -n true && echo ok'
  2. Then run: sudo CONFIRM_ADMIN_LOGIN_TESTED=yes bash ./deploy/harden-ssh.sh
  3. Edit /etc/stockeye/stockeye.env, then run the backend-image workflow to deploy.
MSG
