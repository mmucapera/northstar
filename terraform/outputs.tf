output "resource_group_name" {
  value = azurerm_resource_group.this.name
}

output "storage_account_name" {
  description = "Fill into northstar-deploy/configurations/<customer>/parameters/<env>.yml as {{STORAGE_ACCOUNT}}."
  value       = azurerm_storage_account.this.name
}

output "storage_container_name" {
  value = azurerm_storage_container.extracts.name
}

output "key_vault_uri" {
  description = "Fill into parameters/<env>.yml as {{KEY_VAULT_URI}}."
  value       = azurerm_key_vault.this.vault_uri
}

output "fabric_capacity_name" {
  value = azurerm_fabric_capacity.this.name
}

output "fabric_capacity_id" {
  description = "Full ARM resource ID of the paid F2 capacity. fabric_workspace.this uses this directly unless capacity_display_name is set (see fabric_workspace.tf) to run on the free trial capacity instead."
  value       = azurerm_fabric_capacity.this.id
}

output "spn_tenant_id" {
  description = "Fill into TENANT_ID for auth_spn.py / northstar-flow's .env."
  value       = data.azurerm_client_config.current.tenant_id
}

output "spn_client_id" {
  description = "Fill into CLIENT_ID for auth_spn.py / northstar-flow's .env."
  value       = azuread_application.this.client_id
}

output "spn_client_secret_key_vault_reference" {
  description = "The CLIENT_SECRET itself is not output in plaintext - read it from Key Vault (az keyvault secret show) or via `terraform output -raw spn_client_secret` if you need it directly."
  value       = azurerm_key_vault_secret.spn_client_secret.id
}

output "spn_client_secret" {
  description = "Sensitive - fill into CLIENT_SECRET. Prefer reading it from Key Vault in real use; this exists for first-time setup convenience."
  value       = azuread_application_password.this.value
  sensitive   = true
}

output "workspace_id" {
  description = "Fill into northstar-deploy/configurations/<customer>/config.yml, replacing the 'xxxxxxxx-xxxx-...' workspace_id placeholders."
  value       = fabric_workspace.this.id
}

output "lakehouse_id" {
  description = "The lkh_001 Lakehouse's item ID - needed for northstar-formation's --lakehouse-id flag and northstar-deploy's parameter_replacements OneLake URL substitution."
  value       = fabric_lakehouse.lkh_001.id
}

output "spark_app_url" {
  description = "Project Spark frontend URL, once deployed via `az webapp deploy`."
  value       = "https://${azurerm_linux_web_app.spark.default_hostname}"
}

output "spark_app_name" {
  description = "App Service name - used as the target for `az webapp deploy`/`az webapp log tail`."
  value       = azurerm_linux_web_app.spark.name
}

output "webapp_sql_server_fqdn" {
  description = "Server FQDN of the webapp's own Fabric SQL Database (access logs + login allowlist) - fill into WEBAPP_SQL_SERVER for frontend/scripts/setup-webapp-db.mjs."
  value       = fabric_sql_database.webapp_logs.properties.server_fqdn
}

output "webapp_sql_database_name" {
  value = fabric_sql_database.webapp_logs.properties.database_name
}

output "fabric_sql_endpoint" {
  description = "Lakehouse SQL analytics endpoint FQDN - fill into northstar-formation semantic-model's --sql-endpoint and FABRIC_SQL_ENDPOINT."
  value       = fabric_lakehouse.lkh_001.properties.sql_endpoint_properties.connection_string
}

output "fabric_database_id" {
  description = "Lakehouse SQL analytics endpoint's database id - fill into northstar-formation semantic-model's --database-id and FABRIC_DATABASE_ID."
  value       = fabric_lakehouse.lkh_001.properties.sql_endpoint_properties.id
}

output "next_steps" {
  value = <<-EOT
    1. Fill the workspace_id output above into
       northstar-deploy/configurations/${var.customer_id}/config.yml
       (replacing the "xxxxxxxx-xxxx-..." placeholders).
    2. Fill storage_account_name/key_vault_uri into
       northstar-deploy/configurations/${var.customer_id}/parameters/${var.environment}.yml.
    3. Set TENANT_ID/CLIENT_ID/CLIENT_SECRET (from the outputs above) wherever
       auth_spn.py and northstar-flow read their environment from.
    4. Run northstar-formation's pipelines/notebook generation against this real
       workspace_id/lakehouse_id instead of the placeholder GUID used for
       local verification (see docs/customer0-pilot-kickoff.md).
  EOT
}
