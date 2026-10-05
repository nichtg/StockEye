#!/bin/sh
# docker compose for the production stack, with the right project and env files.
# Installed as /usr/local/sbin/stockeye-compose; used by deploy.sh, backup.sh and the runbook.
exec docker compose --project-name stockeye --env-file /etc/stockeye/stockeye.env \
  --env-file /etc/stockeye/state.env -f /opt/stockeye/compose.yml "$@"
