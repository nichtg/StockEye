#!/bin/sh
# Runs once, when the mongo data volume is first created (official image's initdb hook).
# Creates the least-privilege user the API connects as: readWrite on the stockeye database only.
set -eu
: "${MONGO_APP_USERNAME:?}" "${MONGO_APP_PASSWORD:?}"
# Passwords are generated as hex (see the env template), so they are safe inside a JS string.
mongosh --quiet admin <<JS
db.getSiblingDB("stockeye").createUser({
  user: "${MONGO_APP_USERNAME}",
  pwd: "${MONGO_APP_PASSWORD}",
  roles: [{ role: "readWrite", db: "stockeye" }]
});
JS
