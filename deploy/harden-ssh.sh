#!/usr/bin/env bash
# Second, separate hardening step. Run it ONLY after you have logged in as `admin` over SSH in a
# new terminal and confirmed `sudo -n true` works there. It restricts sshd to the two intended
# accounts, then locks the default `ubuntu` user and removes its sudo rights. Doing this inside
# setup-vm.sh could lock you out of a VM before the admin key was ever tested.
#
#   sudo CONFIRM_ADMIN_LOGIN_TESTED=yes ./deploy/harden-ssh.sh
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin

[[ $EUID -eq 0 ]] || { echo "run as root (sudo)"; exit 1; }
[[ "${CONFIRM_ADMIN_LOGIN_TESTED:-}" == yes ]] || {
  echo "Set CONFIRM_ADMIN_LOGIN_TESTED=yes after logging in as admin from a second terminal."
  exit 1
}
id admin >/dev/null 2>&1 || { echo "no admin user: run setup-vm.sh first"; exit 1; }
[[ -s /home/admin/.ssh/authorized_keys ]] || { echo "admin has no authorized key"; exit 1; }
sudo -u admin sudo -n true || { echo "admin cannot sudo without a password"; exit 1; }

printf 'AllowUsers admin deploy\n' >/etc/ssh/sshd_config.d/20-stockeye-allowusers.conf
if sshd -t; then
  systemctl try-reload-or-restart ssh
else
  rm -f /etc/ssh/sshd_config.d/20-stockeye-allowusers.conf
  echo "sshd config test failed; change removed"
  exit 1
fi

if id ubuntu >/dev/null 2>&1; then
  passwd -l ubuntu >/dev/null
  usermod -s /usr/sbin/nologin ubuntu
  # cloud-init grants the default user passwordless sudo in a drop-in; move it out of the way.
  for f in /etc/sudoers.d/*; do
    [[ -f "$f" ]] || continue
    if grep -Eq '^ubuntu[[:space:]]' "$f"; then
      mv "$f" "$f.disabled-by-stockeye"
      echo "disabled sudo rule file $f"
    fi
  done
  gpasswd -d ubuntu sudo >/dev/null 2>&1 || true
fi
echo "Done: only admin and deploy can log in over SSH; ubuntu is locked and has no sudo."
