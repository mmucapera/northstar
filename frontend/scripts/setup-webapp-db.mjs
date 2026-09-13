// One-time (idempotent - safe to re-run) setup for the webapp's own Fabric
// SQL Database (terraform/fabric_sql_database.tf): creates the WebAccessLog
// and AuthorizedUsers tables (seeding the login allowlist), plus the
// interactive-feature tables added 2026-09-08 (cash-call approvals,
// reconciliation case notes, HSE incident follow-ups, per-user alert
// thresholds, and support tickets) - all keyed on the same natural keys the
// read-only gold.* facts use (PeriodId/FieldId/PartnerId, IncidentId), since
// gold.* itself can't be written to directly (see access-log.ts's header for
// why - same read-only-SQL-endpoint constraint).
//
// No grant/CREATE USER step needed here, unlike the plain Azure SQL Database
// this replaced - Admin/Member/Contributor Fabric workspace roles all get
// db_owner-equivalent access to every SQL database in the workspace
// automatically (confirmed before building this - see
// docs/fabric-environment-setup-log.md). The App Service's managed identity
// already has Contributor on the workspace (terraform/app_service.tf), so it
// can read/write dbo.WebAccessLog and dbo.AuthorizedUsers with zero extra
// setup on the database side.
//
// This script itself runs as the deploy SPN (already a workspace admin -
// see terraform/fabric_workspace.tf) purely to create the schema once.
//
// Required env vars:
//   AZURE_TENANT_ID / AZURE_CLIENT_ID / AZURE_CLIENT_SECRET  - the deploy SPN
//   WEBAPP_SQL_SERVER    - e.g. <guid>.database.fabric.microsoft.com,1433
//   WEBAPP_SQL_DATABASE  - e.g. sqldb_webapp_logs-<guid>
// Optional:
//   SEED_AUTHORIZED_USERS - "email:group,email:group" pairs to seed into
//                            AuthorizedUsers (skipped if unset)

import sql from "mssql";
import { ClientSecretCredential } from "@azure/identity";

const required = ["WEBAPP_SQL_SERVER", "WEBAPP_SQL_DATABASE"];
for (const name of required) {
  if (!process.env[name]) throw new Error(`Missing required env var: ${name}`);
}

const credential = new ClientSecretCredential(
  process.env.AZURE_TENANT_ID,
  process.env.AZURE_CLIENT_ID,
  process.env.AZURE_CLIENT_SECRET,
);
const token = (await credential.getToken("https://database.windows.net/.default")).token;

// Fabric SQL Database's server FQDN comes back as "host,1433" - split it,
// same as frontend/src/data/webapp-db.ts does at runtime.
const [host, port] = process.env.WEBAPP_SQL_SERVER.split(",");

const pool = await sql.connect({
  server: host,
  port: port ? Number(port) : undefined,
  database: process.env.WEBAPP_SQL_DATABASE,
  authentication: { type: "azure-active-directory-access-token", options: { token } },
  options: { encrypt: true },
});

async function exec(label, query) {
  process.stdout.write(`${label} ... `);
  await pool.request().query(query);
  console.log("ok");
}

await exec(
  "Create dbo.WebAccessLog",
  `IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'WebAccessLog' AND schema_id = SCHEMA_ID('dbo'))
   CREATE TABLE dbo.WebAccessLog (
     Id BIGINT IDENTITY(1,1) PRIMARY KEY,
     EventType NVARCHAR(20) NOT NULL,
     EventTimestamp DATETIME2 NOT NULL,
     UserEmail NVARCHAR(200) NULL,
     UserName NVARCHAR(200) NULL,
     UserRole NVARCHAR(50) NULL,
     Path NVARCHAR(500) NULL,
     DurationMs BIGINT NULL,
     Referrer NVARCHAR(500) NULL,
     Ip NVARCHAR(64) NULL,
     UserAgent NVARCHAR(500) NULL,
     Country NVARCHAR(100) NULL,
     City NVARCHAR(100) NULL,
     Continent NVARCHAR(100) NULL,
     CreatedAt DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
   )`,
);
await exec(
  "Index WebAccessLog(EventTimestamp)",
  `IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_WebAccessLog_EventTimestamp')
   CREATE INDEX IX_WebAccessLog_EventTimestamp ON dbo.WebAccessLog (EventTimestamp DESC)`,
);
await exec(
  "Index WebAccessLog(UserEmail)",
  `IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_WebAccessLog_UserEmail')
   CREATE INDEX IX_WebAccessLog_UserEmail ON dbo.WebAccessLog (UserEmail)`,
);

await exec(
  "Create dbo.AuthorizedUsers",
  `IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'AuthorizedUsers' AND schema_id = SCHEMA_ID('dbo'))
   CREATE TABLE dbo.AuthorizedUsers (
     Email NVARCHAR(200) NOT NULL PRIMARY KEY,
     UserGroup NVARCHAR(50) NOT NULL,
     CreatedAt DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
   )`,
);

await exec(
  "Create dbo.CashCallActions",
  `IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'CashCallActions' AND schema_id = SCHEMA_ID('dbo'))
   CREATE TABLE dbo.CashCallActions (
     Id BIGINT IDENTITY(1,1) PRIMARY KEY,
     PeriodId NVARCHAR(7) NOT NULL,
     FieldId NVARCHAR(50) NOT NULL,
     PartnerId NVARCHAR(50) NOT NULL,
     Action NVARCHAR(30) NOT NULL, -- approved | disputed | clarification_requested
     Note NVARCHAR(1000) NULL,
     ActedByEmail NVARCHAR(200) NOT NULL,
     ActedByName NVARCHAR(200) NULL,
     ActedAt DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
   )`,
);
await exec(
  "Index CashCallActions(PeriodId, FieldId, PartnerId)",
  `IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_CashCallActions_Record')
   CREATE INDEX IX_CashCallActions_Record ON dbo.CashCallActions (PeriodId, FieldId, PartnerId)`,
);

await exec(
  "Create dbo.ReconciliationCaseNotes",
  `IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'ReconciliationCaseNotes' AND schema_id = SCHEMA_ID('dbo'))
   CREATE TABLE dbo.ReconciliationCaseNotes (
     Id BIGINT IDENTITY(1,1) PRIMARY KEY,
     PeriodId NVARCHAR(7) NOT NULL,
     FieldId NVARCHAR(50) NOT NULL,
     PartnerId NVARCHAR(50) NOT NULL,
     Note NVARCHAR(1000) NOT NULL,
     AssignedToEmail NVARCHAR(200) NULL,
     Status NVARCHAR(20) NOT NULL DEFAULT 'open', -- open | resolved
     CreatedByEmail NVARCHAR(200) NOT NULL,
     CreatedByName NVARCHAR(200) NULL,
     CreatedAt DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
     UpdatedAt DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
   )`,
);
await exec(
  "Index ReconciliationCaseNotes(PeriodId, FieldId, PartnerId)",
  `IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ReconciliationCaseNotes_Record')
   CREATE INDEX IX_ReconciliationCaseNotes_Record ON dbo.ReconciliationCaseNotes (PeriodId, FieldId, PartnerId)`,
);

await exec(
  "Create dbo.IncidentActions",
  `IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'IncidentActions' AND schema_id = SCHEMA_ID('dbo'))
   CREATE TABLE dbo.IncidentActions (
     Id BIGINT IDENTITY(1,1) PRIMARY KEY,
     IncidentId NVARCHAR(50) NOT NULL,
     Note NVARCHAR(1000) NOT NULL,
     AssignedToEmail NVARCHAR(200) NULL,
     DueDate DATE NULL,
     Status NVARCHAR(20) NOT NULL DEFAULT 'open', -- open | closed
     CreatedByEmail NVARCHAR(200) NOT NULL,
     CreatedByName NVARCHAR(200) NULL,
     CreatedAt DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
     UpdatedAt DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
   )`,
);
await exec(
  "Index IncidentActions(IncidentId)",
  `IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_IncidentActions_IncidentId')
   CREATE INDEX IX_IncidentActions_IncidentId ON dbo.IncidentActions (IncidentId)`,
);

await exec(
  "Create dbo.UserThresholds",
  `IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'UserThresholds' AND schema_id = SCHEMA_ID('dbo'))
   CREATE TABLE dbo.UserThresholds (
     Email NVARCHAR(200) NOT NULL,
     MetricKey NVARCHAR(50) NOT NULL, -- variance_watch_pct | variance_investigate_pct | downtime_alert_hours | uptime_alert_pct
     ThresholdValue DECIMAL(9,3) NOT NULL,
     UpdatedAt DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
     PRIMARY KEY (Email, MetricKey)
   )`,
);

await exec(
  "Create dbo.Tickets",
  `IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'Tickets' AND schema_id = SCHEMA_ID('dbo'))
   CREATE TABLE dbo.Tickets (
     Id BIGINT IDENTITY(1,1) PRIMARY KEY,
     Subject NVARCHAR(200) NOT NULL,
     Description NVARCHAR(MAX) NOT NULL,
     Category NVARCHAR(30) NOT NULL, -- technical | finance | ops | hse
     Status NVARCHAR(20) NOT NULL DEFAULT 'open', -- open | in_progress | closed
     CreatedByEmail NVARCHAR(200) NOT NULL,
     CreatedByName NVARCHAR(200) NULL,
     CreatedAt DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
     UpdatedAt DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
   )`,
);
await exec(
  "Index Tickets(Status)",
  `IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Tickets_Status')
   CREATE INDEX IX_Tickets_Status ON dbo.Tickets (Status)`,
);

await exec(
  "Create dbo.SavedForecasts",
  `IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'SavedForecasts' AND schema_id = SCHEMA_ID('dbo'))
   CREATE TABLE dbo.SavedForecasts (
     Id BIGINT IDENTITY(1,1) PRIMARY KEY,
     Email NVARCHAR(200) NOT NULL,
     Name NVARCHAR(100) NOT NULL,
     PeriodId NVARCHAR(20) NOT NULL,
     UptimeAdjustment DECIMAL(6,2) NOT NULL,
     ForecastAdjustment DECIMAL(6,2) NOT NULL,
     CreatedAt DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
   )`,
);
await exec(
  "Index SavedForecasts(Email)",
  `IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_SavedForecasts_Email')
   CREATE INDEX IX_SavedForecasts_Email ON dbo.SavedForecasts (Email)`,
);

await exec(
  "Create dbo.UserDashboardLayout",
  `IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'UserDashboardLayout' AND schema_id = SCHEMA_ID('dbo'))
   CREATE TABLE dbo.UserDashboardLayout (
     Email NVARCHAR(200) NOT NULL,
     Page NVARCHAR(50) NOT NULL, -- e.g. "overview" - one row per page a layout applies to
     LayoutJson NVARCHAR(MAX) NOT NULL, -- JSON array of widget ids, in the user's chosen order
     UpdatedAt DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
     PRIMARY KEY (Email, Page)
   )`,
);

const seed = process.env.SEED_AUTHORIZED_USERS;
if (seed) {
  const pairs = seed.split(",").map((s) => s.trim()).filter(Boolean);
  for (const pair of pairs) {
    const [email, group] = pair.split(":").map((s) => s.trim());
    if (!email || !group) continue;
    await pool
      .request()
      .input("email", sql.NVarChar, email.toLowerCase())
      .input("group", sql.NVarChar, group)
      .query(`
        MERGE dbo.AuthorizedUsers AS target
        USING (SELECT @email AS Email, @group AS UserGroup) AS src
        ON target.Email = src.Email
        WHEN MATCHED THEN UPDATE SET UserGroup = src.UserGroup
        WHEN NOT MATCHED THEN INSERT (Email, UserGroup) VALUES (src.Email, src.UserGroup);
      `);
    console.log(`Seeded authorized user: ${email} (${group})`);
  }
} else {
  console.log("SEED_AUTHORIZED_USERS not set - skipping seed step.");
}

console.log("\nDone.");
await pool.close();
