# Project Spark (Lovable/TanStack Start frontend) - hosted on Azure App
# Service, no Docker. Node server output comes from Nitro's node-server
# preset (see Project Spark/vite.config.ts) - `node .output/server/index.mjs`,
# listening on the PORT env var App Service sets automatically.
#
# Phase 2: wired to real gold.* data via the lakehouse's SQL analytics
# endpoint. No secrets stored anywhere - the app authenticates to the SQL
# endpoint (read) and the webapp SQL database (read+write) as its own
# system-assigned managed identity (DefaultAzureCredential), granted a role
# on the Fabric workspace below.
#
# Role is Contributor - the app writes to fabric_sql_database.webapp_logs
# (access logs + login allowlist, see access-log.ts/auth-check.ts) as well as
# reading gold.* through the lakehouse's SQL analytics endpoint
# (fabric-data.ts). Admin/Member/Contributor workspace roles all get
# db_owner-equivalent access to every SQL database in the workspace
# automatically (no CREATE USER/Directory Readers step, unlike the plain
# Azure SQL Database this replaced) - Contributor is the smallest of the
# three that still grants write.

variable "app_service_sku" {
  description = "App Service Plan SKU for the Project Spark frontend."
  type        = string
  default     = "B1" # cheapest Linux SKU that supports always-on; fine for a pilot demo
}

resource "azurerm_service_plan" "spark" {
  name                = "asp-${local.name_prefix}-spark"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  os_type             = "Linux"
  sku_name            = var.app_service_sku

  tags = local.merged_tags
}

resource "azurerm_linux_web_app" "spark" {
  name                = "app-${local.name_prefix}-spark"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  service_plan_id     = azurerm_service_plan.spark.id

  site_config {
    application_stack {
      node_version = "22-lts"
    }
    # Explicit startup command - Oryx's default Node auto-detection looks for
    # server.js/package.json "main" at the repo root, which won't find
    # Nitro's node-server output at .output/server/index.mjs.
    app_command_line  = "node .output/server/index.mjs"
    always_on         = true
    use_32_bit_worker = false
  }

  app_settings = {
    # Oryx builds the app server-side on deploy (npm install && npm run
    # build) instead of us shipping node_modules/.output in the zip.
    SCM_DO_BUILD_DURING_DEPLOYMENT = "true"
    # Oryx's Node build only runs `npm run build` when this is set; also
    # tells Oryx which script starts the app post-build.
    POST_BUILD_SCRIPT_PATH   = ""
    WEBSITE_RUN_FROM_PACKAGE = "0" # must be unset/0 - Oryx build-on-deploy is incompatible with run-from-package

    # Neither of these is a secret - the connection itself authenticates via
    # this app's own managed identity (see the identity block + role
    # assignment below), no client secret involved anywhere.
    FABRIC_SQL_ENDPOINT = fabric_lakehouse.lkh_001.properties.sql_endpoint_properties.connection_string
    FABRIC_DATABASE_ID  = fabric_lakehouse.lkh_001.properties.sql_endpoint_properties.id

    # Used for the OneLake DFS (ADLS Gen2) write path - access-log events -
    # not secrets, just addressing (auth is via managed identity).
    FABRIC_WORKSPACE_ID = fabric_workspace.this.id
    FABRIC_LAKEHOUSE_ID = fabric_lakehouse.lkh_001.id

    # The AI assistant's LLM API key. Originally wired as a Key Vault
    # reference (@Microsoft.KeyVault(...) - see azurerm_key_vault_secret.groq_api_key
    # and azurerm_role_assignment.spark_app_kv_secrets_user in key_vault.tf),
    # but that reference got stuck on AccessToKeyVaultDenied for 50+ minutes
    # in this tenant despite a verified-correct role assignment (role,
    # principal, scope, network ACLs all checked out) - a tenant-specific RBAC
    # propagation quirk, consistent with the personal-MSA-tenant friction
    # documented elsewhere in docs/fabric-environment-setup-log.md. Falling
    # back to a bare app setting (still encrypted at rest by App Service,
    # still never committed to git - see terraform.tfvars) to unblock the
    # free-tier placeholder key now. The Key Vault plumbing is left in place
    # to revisit once the RBAC issue is understood.
    GROQ_API_KEY = var.groq_api_key

    # Webapp's own operational SQL DB (access logs + login allowlist) - a
    # Fabric SQL Database, not a separate Azure resource - see
    # fabric_sql_database.tf. Not a secret - auth is this app's managed
    # identity via its Fabric workspace role (Contributor, below).
    WEBAPP_SQL_SERVER   = fabric_sql_database.webapp_logs.properties.server_fqdn
    WEBAPP_SQL_DATABASE = fabric_sql_database.webapp_logs.properties.database_name
  }

  identity {
    type = "SystemAssigned"
  }

  logs {
    application_logs {
      file_system_level = "Information"
    }
    http_logs {
      file_system {
        retention_in_days = 7
        retention_in_mb   = 35
      }
    }
  }

  tags = local.merged_tags
}

# Grants the App Service's own managed identity read access to query gold.*
# via the SQL analytics endpoint - same fabric_workspace_role_assignment
# mechanism already used for admin_users/admin_spns in fabric_workspace.tf. A
# managed identity is just another AAD service principal, so "ServicePrincipal"
# is the correct principal type here too.
resource "fabric_workspace_role_assignment" "spark_app_viewer" {
  workspace_id = fabric_workspace.this.id
  principal = {
    id   = azurerm_linux_web_app.spark.identity[0].principal_id
    type = "ServicePrincipal"
  }
  role = "Contributor"
}
