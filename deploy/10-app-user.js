// Runs once, when the mongo data volume is first created. The official image's entrypoint runs
// *.js init files through an authenticated mongosh (as the root user it just created), so
// createUser is allowed. Creates the least-privilege user the API connects as: readWrite on the
// stockeye database only. process.env keeps the password out of any command line.
const user = process.env.MONGO_APP_USERNAME;
const pwd = process.env.MONGO_APP_PASSWORD;
if (!user || !pwd) {
  throw new Error("MONGO_APP_USERNAME and MONGO_APP_PASSWORD must be set");
}
db.getSiblingDB("stockeye").createUser({
  user: user,
  pwd: pwd,
  roles: [{ role: "readWrite", db: "stockeye" }],
});
