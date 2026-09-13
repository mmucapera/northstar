# A real, writable database for the webapp's own operational data: access
# logs (login/logout/page-visit events) and the login allowlist. Lives
# inside the Fabric workspace itself (not a separate Azure SQL Server) -
# visible in the Fabric portal alongside the Lakehouse/semantic model, one
# fewer Azure resource to manage, and access is granted the same way as
# everything else here (fabric_workspace_role_assignment), not via a
# separate AAD-database-user dance.
#
# Confirmed before building this: Admin/Member/Contributor workspace roles
# all get db_owner-equivalent access to every SQL database in the workspace
# automatically - no CREATE USER / Directory Readers step needed (that
# requirement is specific to plain Azure SQL Database, which this replaces -
# see docs/fabric-environment-setup-log.md for why that path was dropped).
#
# Filed under data_engineering/webapp_logs - reuses the data_engineering
# folder lookup from fabric_lakehouse.tf (same bootstrapping caveat applies:
# that folder only exists after at least one northstar-deploy publish for this
# customer).
resource "fabric_folder" "webapp_logs" {
  display_name     = "webapp_logs"
  workspace_id     = fabric_workspace.this.id
  parent_folder_id = local.data_engineering_folder_id
}

resource "fabric_sql_database" "webapp_logs" {
  display_name = "sqldb_webapp_logs"
  workspace_id = fabric_workspace.this.id
  description  = "Northstar ${var.customer_id} pilot - webapp access logs + login allowlist. Not part of the medallion pipeline."
  folder_id    = fabric_folder.webapp_logs.id

  configuration = {
    creation_mode = "New"
  }
}
