// Server-only: shared connection helper for the webapp's own Fabric SQL
// Database (terraform/fabric_sql_database.tf) - access logs
// (access-log.ts) and the login allowlist (auth-check.ts) both use this.
//
// Auth is this app's own managed identity via its Fabric workspace role
// (Contributor - see app_service.tf) - no CREATE USER/password anywhere.

export async function connectWebappDb() {
  const server = process.env["WEBAPP_SQL_SERVER"];
  const database = process.env["WEBAPP_SQL_DATABASE"];
  if (!server || !database) {
    throw new Error("WEBAPP_SQL_SERVER / WEBAPP_SQL_DATABASE not configured");
  }

  const [{ default: sql }, { DefaultAzureCredential }] = await Promise.all([
    import("mssql"),
    import("@azure/identity"),
  ]);

  // Fabric SQL Database's server FQDN comes back as "host,1433" (classic SQL
  // Server host,port notation) - node-mssql's `server` option wants a bare
  // hostname, with the port passed separately via `port`. Passing the whole
  // "host,1433" string through as `server` looks like it should work (it's
  // valid connection-string syntax elsewhere) but silently fails to resolve
  // here - split it explicitly rather than assume.
  const [host, port] = server.split(",");

  const credential = new DefaultAzureCredential();
  const tokenResponse = await credential.getToken("https://database.windows.net/.default");
  if (!tokenResponse) throw new Error("Failed to acquire an Azure AD token for the webapp SQL DB");

  return sql.connect({
    server: host!,
    port: port ? Number(port) : undefined,
    database,
    authentication: { type: "azure-active-directory-access-token", options: { token: tokenResponse.token } },
    options: { encrypt: true },
  });
}
