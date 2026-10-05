# Deploying StockEye for $0

The frontend is a static site on GitHub Pages. The backend (Caddy, the API and MongoDB) runs in Docker on an
Oracle Cloud Always Free Arm VM. GitHub Actions builds the API image and deploys it over SSH.

```
browser --https--> GitHub Pages (static SPA, <org>.github.io)
   |
   +--https, bearer token--> https://<PUBLIC_IP>/api  --> Caddy (80/443) --> api:8000 --> mongo (internal only)
```

Things marked **verify:** were written from documentation and could not be tested without an Oracle account. Check
them the first time and fix this file if they differ.

Naming used below: `<org>` is your GitHub organization, `<PUBLIC_IP>` the VM's reserved public IP.

## One-time setup (in this order)

### 1. GitHub organization and repository
1. Create a free GitHub organization (github.com > your avatar > Your organizations > New). A dedicated origin
   (`<org>.github.io`) means no other Pages site shares the browser storage or origin of the app.
2. Transfer the repository to the organization (repo Settings > General > Danger Zone > Transfer).
3. **Scan before going public.** Actions > `gitleaks` > Run workflow. It scans the full git history. Do not continue
   until it is green. If it finds something, rotate that credential first, then clean the history.
4. Make the repository public (Settings > General > Danger Zone).
5. Right away: Settings > Code security: enable **Secret scanning** and **Push protection**, and Dependabot alerts.
6. Settings > Branches > add a rule for `main`: require a pull request, block force pushes, and require these status
   checks (the exact names GitHub shows once each has run once; **verify:** the reusable-workflow name):
   `backend / gates`, `frontend-check`, `docker-build (backend)`, `docker-build (frontend)`, `gitleaks`,
   `deploy-smoke`.
   These workflows deliberately have no `paths:` filter: a required check from a path-filtered workflow never
   reports on a PR that does not touch those paths, and GitHub would then block the merge forever. Running every
   check on every PR costs a few minutes and is the simplest correct setup.
7. Settings > Environments > New environment `production`. Add a required reviewer (yourself) so each deploy waits
   for a click. Restrict it to the `main` branch.

### 2. Oracle Cloud account
1. Sign up at oracle.com/cloud/free. Pick a home region carefully: it cannot be changed, and Always Free Arm
   capacity varies by region.
2. **Upgrade to Pay-As-You-Go** (Billing > Upgrade). Idle Always Free instances on a pure free-tier account can be
   reclaimed; a PAYG account is not, and resources inside the Always Free limits are still charged $0. Create a
   budget alert of $1 (Billing > Budgets) as a safety net. **verify:** current Oracle reclaim and PAYG wording.
3. Create a private Object Storage bucket (Storage > Buckets) named e.g. `stockeye-backups`, default visibility
   **Private**. Note your Object Storage **namespace** (Profile > Tenancy details).

### 3. The VM
1. Compute > Instances > Create. Image: Ubuntu 24.04 (aarch64). Shape: `VM.Standard.A1.Flex`, 1 OCPU and 6 GB RAM is
   plenty (the free limit is 4 OCPU / 24 GB). If you get "Out of capacity", retry later or in another availability
   domain. Add your SSH public key.
2. Networking > Reserved public IPs > Create, then attach it to the instance's VNIC (instance > Attached VNICs >
   IPv4 addresses > Edit > Reserved public IP). This is `<PUBLIC_IP>`. It must not change.
3. Security list (or network security group) of the VM's subnet: ingress TCP **22, 80, 443** from `0.0.0.0/0`, and
   nothing else. Port 80 is required: Let's Encrypt validates the certificate over it.
4. SSH in as `ubuntu` with your key.
5. Create the CI deploy key on **your own computer** (never on the VM):
   `ssh-keygen -t ed25519 -f stockeye-deploy -N "" -C github-deploy`. You will paste `stockeye-deploy.pub` into the
   next step and `stockeye-deploy` (the private half) into GitHub in step 6.

### 4. Run the VM setup script
On the VM:
```bash
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/<org>/StockEye.git && cd StockEye
less deploy/setup-vm.sh          # read it; it changes sshd, firewall and sudo rules
sudo ADMIN_PUBKEY='ssh-ed25519 AAAA... you@laptop' \
     DEPLOY_PUBKEY='ssh-ed25519 AAAA... github-deploy' \
     bash ./deploy/setup-vm.sh
```
(`DEPLOY_PUBKEY` is the one line from `stockeye-deploy.pub`. The scripts are also marked executable, so
`sudo ... ./deploy/setup-vm.sh` works; `sudo bash` is the fallback if a copy lost the mode.)

It installs unattended upgrades (automatic reboot at 04:00 server time), makes sshd key-only with no root login,
opens 22/80/443 by editing `/etc/iptables/rules.v4` and the live rules (it never runs `netfilter-persistent save`,
which would also save Docker's own chains), installs Docker from Docker's apt repo (checking its key fingerprint),
creates the `admin` and `deploy` users, installs the deploy and backup scripts, blocks containers from the cloud
metadata service (below), and starts a nightly backup timer. It ends by printing the SSH host key fingerprint and a
`known_hosts` line. Keep that output.

**Metadata block.** Containers must not be able to reach `169.254.169.254`, or a bug in the API could be used to
fetch the VM's instance-principal credentials. `stockeye-docker-user.service` adds
a `DROP` for `169.254.0.0/16` to the `DOCKER-USER` chain after `docker.service` on every boot and is `PartOf` Docker,
so it is re-applied after a Docker restart as well; it is idempotent and is not saved into `/etc/iptables`. On Oracle
the VCN DNS resolver is also `169.254.169.254` (port 53), so DNS to it is let through ahead of the drop; without that,
containers could not resolve names (no certificate, no market data).
Checks: `sudo iptables -S DOCKER-USER` shows the two port-53 `RETURN` rules before the `DROP`, and
`sudo stockeye-compose exec caddy nslookup acme-v02.api.letsencrypt.org` resolves. The `deploy-smoke` workflow tests
the metadata block on a CI runner (whose DNS is elsewhere, so the DNS exception is only verified here).

**Lock down SSH (second step).** Re-running setup is safe (it never overwrites `/etc/stockeye/stockeye.env`; re-run it
after pulling a new compose file). But first, from a **second terminal**, confirm
`ssh admin@<PUBLIC_IP> 'sudo -n true && echo ok'` prints `ok`. Only then, on the VM:
```bash
sudo CONFIRM_ADMIN_LOGIN_TESTED=yes bash ./deploy/harden-ssh.sh
```
It sets `AllowUsers admin deploy`, locks the default `ubuntu` user and removes its sudo rule. (It is separate so a
mistake in the admin key cannot lock you out before you tested it. If you are locked out anyway, use the Oracle
console's serial console or re-attach the boot volume to recover.)

Then fill in the secrets file:
```bash
sudo -e /etc/stockeye/stockeye.env
```
Each line has a comment saying how to generate it (`openssl rand -hex 24` for the Mongo passwords, `openssl rand -hex 32`
for the JWT secret). Set `PUBLIC_IP`, `GHCR_IMAGE=ghcr.io/<org lowercase>/stockeye-api`, the CORS origin
`'["https://<org>.github.io"]'`, the optional market-data keys, and the backup `OCI_NAMESPACE` / `OCI_BACKUP_BUCKET`.
The file is `root:root 0600`; the deploy script refuses to run while any `CHANGE_ME` is left.

### 5. Backup permissions in Oracle (instance principal)
The VM uploads backups as itself, so there is no API key on it.
1. Identity > Domains > (your domain) > Dynamic groups > Create `stockeye-vm` with the rule
   `ANY {instance.id = '<the instance OCID>'}`.
2. Identity > Policies > Create, in the compartment holding the bucket (**verify:** exact syntax):
   ```
   Allow dynamic-group stockeye-vm to manage objects in compartment <compartment> where all {target.bucket.name='stockeye-backups', any {request.permission='OBJECT_CREATE', request.permission='OBJECT_INSPECT'}}
   ```
   (Upload only; the VM cannot read or delete old backups, so a compromised VM cannot destroy them.)
3. **Retention:** bucket > Lifecycle policy rules > Create rule: action *Delete*, target *Objects*, *30 days* after
   creation. That is the cleanup of old copies (the VM itself keeps the last 7 locally). Optionally add a Retention
   rule (bucket > Retention rules, 14 days) so nobody can delete a fresh backup early; it cannot be shortened once
   locked.
4. Test: `sudo systemctl start stockeye-backup.service` after the first deploy, then `journalctl -u stockeye-backup`
   and check the object appears in the bucket. **verify:** the `oci` upload works with instance principal.

### 6. GitHub settings for deployment
Settings > Secrets and variables > Actions.

Repository **variables** (public config, not secrets):

| Variable | Value |
|---|---|
| `API_HOST` | `<PUBLIC_IP>` |
| `API_ORIGIN` | `https://<PUBLIC_IP>` (no trailing slash; the build appends `/api`) |
| `PAGES_BASE_PATH` | `/StockEye/` for a project site (`https://<org>.github.io/StockEye/`), or `/` |
| `DEPLOY_KNOWN_HOSTS` | the `known_hosts` line the setup script printed: `<PUBLIC_IP> ssh-ed25519 AAAA...` |

Environment `production` > **secret** `DEPLOY_SSH_KEY`: the full contents of the private file `stockeye-deploy`.
Then delete that file from your computer (or keep it in a password manager).

Pin check: compare `DEPLOY_KNOWN_HOSTS` against the fingerprint the script printed (`ssh-keygen -lf` of the key).
Never fill it with `ssh-keyscan` output you did not verify: an unverified key defeats the point of pinning.

### 7. First deploy, GHCR visibility and Pages
1. Actions > `backend-image` > Run workflow on `main` (approve the `production` deployment). It tests, builds the
   arm64 image, pushes `ghcr.io/<org>/stockeye-api`, and deploys the digest over SSH.
2. The first push creates the package as private. Organization page > Packages > `stockeye-api` > Package settings >
   Change visibility > **Public**, so the VM can pull without credentials. (The image holds no secrets: they come
   only from the env file.) Re-run the workflow's `deploy` job (or the whole workflow) afterwards.
3. Settings > Pages > Source: **GitHub Actions**. Then run Actions > `pages` > Run workflow.
4. On the VM check `sudo stockeye-compose ps`. All three services should be `healthy`. Caddy gets the certificate on
   its first start; `sudo stockeye-compose logs caddy` should show it obtained one for `<PUBLIC_IP>`.
   **verify:** that Let's Encrypt issues IP-address certificates with the `shortlived` profile for your Caddy
   version (needs Caddy 2.10 or later; the compose file pins 2.11) and that the no-SNI handshake from a browser
   gets the certificate (`default_sni` in `deploy/Caddyfile`).

### 8. Create the admin user
No password is ever put in a file or environment variable: the command asks for it with a hidden prompt.
```bash
sudo stockeye-compose exec -it api python -m app.cli create-admin --email you@example.com
```
(`stockeye-compose` is a small wrapper installed by the setup script around
`docker compose --project-name stockeye --env-file ... -f /opt/stockeye/compose.yml`, so it works the same as
`docker compose exec`.) Never set `STOCKEYE_ADMIN_PASSWORD`.

## How a deploy works
`backend-image.yml` (push to `main` touching `backend/`): `test` (the same gates as CI) -> `image` (arm64 build on a
native Arm runner, push to GHCR, output the digest) -> `deploy` (SSH to `deploy@<PUBLIC_IP>` with the digest as the
command). The `deploy` user's key is locked by `authorized_keys` to
`command="/usr/bin/sudo /usr/local/sbin/stockeye-deploy",restrict`: no shell, no forwarding, no pty. The script
accepts only `sha256:` plus 64 hex characters, pulls that digest, records it in `/etc/stockeye/state.env`, runs
`docker compose up -d`, waits up to 3 minutes for the API to be healthy (the image's HEALTHCHECK: HTTP 200 *and* the API can reach MongoDB) and otherwise restores the previous digest. Afterwards it deletes older `stockeye-api` images.
It logs to syslog (`journalctl -t stockeye-deploy`).

The sudo rule allows exactly that one script with no arguments and keeps only `SSH_ORIGINAL_COMMAND`. A group
instead (for example the `docker` group) would give the CI key root on the VM, so the one-script rule is narrower.
`pages.yml` (push touching `frontend/`) builds with the repository variables, fails the build if `dist/` contains
secret-looking strings or source maps, and publishes with GitHub's OIDC deploy.

## Rotating secrets
Always edit with `sudo -e /etc/stockeye/stockeye.env`, then apply with the command shown.

| Secret | How |
|---|---|
| `STOCKEYE_JWT_SECRET` | New value (`openssl rand -hex 32`), then `sudo stockeye-compose up -d api`. All users are signed out. |
| Market-data API keys | Get a new key from the provider, edit the line, `sudo stockeye-compose up -d api`, revoke the old key. |
| `MONGO_APP_PASSWORD` | Open an interactive shell that asks for the root password (no password in a command line or shell history): `sudo stockeye-compose exec -it mongo sh -c 'exec mongosh admin -u "$MONGO_INITDB_ROOT_USERNAME" --authenticationDatabase admin'` (type the root password from the env file when asked), then in mongosh: `db.getSiblingDB("stockeye").changeUserPassword("stockeye_app", passwordPrompt())` and type the new password (also put it in the env file; use hex: `openssl rand -hex 24`). Then `sudo stockeye-compose up -d --force-recreate api`. |
| `MONGO_ROOT_PASSWORD` | Same interactive shell, then `db.getSiblingDB("admin").changeUserPassword("<root user>", passwordPrompt())`. Update the env file and recreate mongo so the backup script sees the new value: `sudo stockeye-compose up -d --force-recreate mongo`. |
| CI deploy key | Make a new key pair on your computer, replace the key in `/home/deploy/.ssh/authorized_keys` by re-running `setup-vm.sh` with the new `DEPLOY_PUBKEY`, update the `DEPLOY_SSH_KEY` environment secret. |
| VM host key | `sudo rm /etc/ssh/ssh_host_* && sudo dpkg-reconfigure openssh-server`, then update the `DEPLOY_KNOWN_HOSTS` variable with the new key. |
| Admin password | Run `create-admin` again with the same email; it promotes/updates the account. **verify:** that it also resets the password in your version. |

## Teardown (order matters)
1. Delete the `API_ORIGIN` / `API_HOST` repository variables and disable Pages (Settings > Pages > unpublish), so
   nothing points at the IP any more. Never release a reserved IP that the deployed frontend still points at: the
   next holder of that address could receive your users' tokens.
2. On the VM: `sudo stockeye-compose down -v` if you want the data gone (take a backup first).
3. Terminate the instance, delete the bucket contents and bucket, then release the reserved IP last.
4. Remove the dynamic group and policy, and the `production` environment.

## Restoring a backup
1. Download from the bucket (Console > bucket > object > Download, or `oci os object get --auth instance_principal ...`
   on the VM), or take the newest local copy in `/var/backups/stockeye/`.
2. Stop writers: `sudo stockeye-compose stop api`.
3. Restore (replaces existing documents with the dump's):
   ```bash
   sudo stockeye-compose exec -T mongo sh -c 'umask 077; cfg="$(mktemp)"; trap "rm -f \"$cfg\"" EXIT; printf "password: %s\n" "$MONGO_INITDB_ROOT_PASSWORD" >"$cfg"; mongorestore --config="$cfg" --username "$MONGO_INITDB_ROOT_USERNAME" --authenticationDatabase admin --archive --gzip --drop' < /var/backups/stockeye/stockeye-<timestamp>.archive.gz
   ```
4. `sudo stockeye-compose start api`. Practice this once on the live VM before you need it. The dump contains password
   hashes and token hashes: treat the file as a secret.

## Go-live probes
Run these from your own computer after the first full deploy. All should pass.
1. **Cookie-only request is rejected.** `curl -sk -o /dev/null -w '%{http_code}\n' -H 'Cookie: access_token=x' https://<PUBLIC_IP>/api/me`
   returns `401` (auth is bearer-only).
2. **Two tabs refresh without logging out.** Log in, open the site in two tabs, wait for the 15-minute access token
   to expire (or clear it), and use both tabs. Neither should be sent to the login page.
3. **A spoofed `X-Forwarded-For` is ignored.** Send 15 quick login attempts with
   `-H 'X-Forwarded-For: 1.2.3.4'`, then repeat with a different forged value. The rate limit (HTTP 429) must still
   trigger, because the limiter sees your real IP, not the forged one. Also `sudo stockeye-compose logs api` should show
   your address.
4. **MongoDB is unreachable from outside.** `nmap -Pn -p- <PUBLIC_IP>` shows only 22, 80 and 443 open; `nc -vz <PUBLIC_IP> 27017`
   fails.
5. **CORS.** `curl -si -H 'Origin: https://evil.example' https://<PUBLIC_IP>/api/health` and the same with
   `-H 'Origin: null'` must not return `access-control-allow-origin`. The same request with
   `Origin: https://<org>.github.io` must.
6. **Framing is hidden.** Embed the site in an `<iframe>` on any test page (e.g. a local HTML file): the app should show
   nothing, not the login form.
7. **TLS and headers.** Run `curl -sI https://<PUBLIC_IP>/api/health`: expect `x-content-type-options: nosniff`, the
   `referrer-policy` header, and no `server` header. (Caddy also sends `strict-transport-security`, but browsers
   ignore HSTS for IP-address hosts, so it gives no protection here; HTTPS-only comes from the app only ever being
   called at `https://` URLs, which the `pages` build enforces.) `curl -si https://<PUBLIC_IP>/` returns 404. Run
   `testssl.sh` or SSL Labs equivalent (SSL Labs does not scan bare IPs; use testssl.sh) and expect TLS 1.2+ only.
   `http://<PUBLIC_IP>/api/health` should redirect to HTTPS.
8. **Repository hygiene.** The `gitleaks` workflow is green on `main`; the `pages` build's secret-pattern step passed;
   Settings > Code security shows secret scanning and push protection on.

## Monitoring
`healthcheck.yml` runs daily and on demand. It fetches `https://<PUBLIC_IP>/api/health` with normal certificate
verification and fails (so GitHub emails you) if the API or database is not ok, or if the certificate has under 36
hours left. Caddy renews the 6-day certificate with about 2 days left, so a 3-day threshold would alert on every
healthy renewal; 36 hours means renewal has really been failing. GitHub disables scheduled workflows after 60 days
without repository activity; if the emails stop, check the Actions tab.

### Weekly check (the daily workflow cannot see the VM)
The healthcheck only sees the public API. It cannot tell that the nightly backup stopped. Once a week, on the VM:
```bash
systemctl list-timers stockeye-backup.timer     # NEXT and LAST look sane
ls /var/lib/stockeye/BACKUP_FAILED 2>&1          # must say "No such file"
journalctl -u stockeye-backup --since "8 days ago" | tail
```
and in the Oracle console check that the newest object in the bucket is from last night. A failed backup also logs
`BACKUP FAILED` at crit level (`journalctl -p crit -t stockeye-backup`) and leaves the marker file until the next
good backup.

### Disk
Log files rotate (compose `local` driver, 10 MB x 3 per service). After each successful deploy the script removes
every `stockeye-api` image except the new one and the previous one. Check `df -h /` occasionally.

## Accepted risks
- A stolen `DEPLOY_SSH_KEY` can only deploy an image digest that exists in the public GHCR package, but anyone with
  push access to `main` (or the `production` approval) can ship arbitrary code. Keep branch protection and the
  environment reviewer on.
- The `admin` SSH key is root on the VM (passwordless sudo). Protect it with a passphrase.
- XSS on the Pages site could ride a signed-in session; mitigated by the strict CSP, short access tokens, refresh
  rotation and reuse detection.
- The refresh token lives in `localStorage` (readable by any script on the origin).
- Registration enumeration is rate limited but possible; a 15-minute lockout can be triggered against a known email.
- Single VM, single region: there is no failover. Backups are nightly, so up to a day of data can be lost.
  Backups are encrypted by Oracle at rest but not client-side.
- Docker-published ports bypass the host's iptables INPUT rules; Mongo is protected by having no published port and
  an internal-only network, and the Oracle security list is the real perimeter.
- HSTS is sent but browsers ignore it for IP-address hosts: it is not a protection here.
- The OCI CLI is installed from a hash-pinned requirements file (`deploy/oci-cli.requirements.txt`, generated with
  `uv pip compile --generate-hashes`), so installs are reproducible, but it is not auto-updated: regenerate it
  yourself now and then.
- An IP-address certificate has no domain name: browsers show the address, and losing the reserved IP means a new
  certificate, a new `API_ORIGIN` and a rebuild of the frontend.
- Unattended upgrades cover Ubuntu and Docker's apt repo (a Docker Engine upgrade restarts the containers briefly).
  The pinned images (Dependabot proposes updates) and the OCI CLI are updated by you; Caddy, Mongo and the Python
  base images are pinned by digest.
- `restart: unless-stopped` plus the 04:00 automatic reboot cause a short outage when a kernel update lands.
