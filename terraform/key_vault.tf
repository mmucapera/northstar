# Key Vault - holds the SPN client secret and (later) any DB connection
# strings. RBAC authorization, not legacy access policies.

resource "azurerm_key_vault" "this" {
  name                       = substr("kv-${local.name_prefix}", 0, 24)
  resource_group_name        = azurerm_resource_group.this.name
  location                   = azurerm_resource_group.this.location
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  purge_protection_enabled   = false # demo/dev only - enable for a real prod tenant
  soft_delete_retention_days = 7

  tags = local.merged_tags
}

resource "azurerm_role_assignment" "deployer_kv_admin" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Administrator"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_role_assignment" "spn_kv_secrets_officer" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = azuread_service_principal.this.object_id
}

resource "azurerm_key_vault_secret" "spn_client_secret" {
  name         = "${var.customer_id}-spn-client-secret"
  value        = azuread_application_password.this.value
  key_vault_id = azurerm_key_vault.this.id

  depends_on = [azurerm_role_assignment.deployer_kv_admin]
}

resource "azurerm_key_vault_secret" "groq_api_key" {
  name         = "${var.customer_id}-groq-api-key"
  value        = var.groq_api_key
  key_vault_id = azurerm_key_vault.this.id

  depends_on = [azurerm_role_assignment.deployer_kv_admin]
}

# Lets the App Service's own managed identity resolve the
# @Microsoft.KeyVault(...) app-setting reference in app_service.tf - without
# this role, that reference silently fails to resolve at runtime.
resource "azurerm_role_assignment" "spark_app_kv_secrets_user" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_linux_web_app.spark.identity[0].principal_id
}
