# ADLS Gen2 storage account - lands customer extract ZIPs for the ADLS poller
# (northstar-flow/app/services/adls_poller.py) and backs OneLake shortcuts.

resource "azurerm_storage_account" "this" {
  name                     = local.storage_account_name
  resource_group_name      = azurerm_resource_group.this.name
  location                 = azurerm_resource_group.this.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"
  is_hns_enabled           = true # required for ADLS Gen2 (hierarchical namespace)
  min_tls_version          = "TLS1_2"

  tags = local.merged_tags
}

resource "azurerm_storage_container" "extracts" {
  name                  = "extracts"
  storage_account_id    = azurerm_storage_account.this.id
  container_access_type = "private"
}

resource "azurerm_role_assignment" "spn_storage_contributor" {
  scope                = azurerm_storage_account.this.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azuread_service_principal.this.object_id
}
