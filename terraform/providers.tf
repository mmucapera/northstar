provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = true
      recover_soft_deleted_key_vaults = true
    }
  }
}

provider "azuread" {}

data "azurerm_client_config" "current" {}

# Authenticates as the SPN this module creates (service_principal.tf), NOT
# the personal account running `terraform apply` - Fabric's own APIs reject
# personal Microsoft accounts outright (confirmed the hard way setting up
# the CUSTOMER0 pilot - see docs/fabric-environment-setup-log.md). This only
# works once a tenant Fabric admin has enabled "Service principals can use
# Fabric APIs" for this SPN in the Fabric Admin Portal - no API/Terraform
# equivalent for that toggle, it's a manual one-time step.
provider "fabric" {
  tenant_id     = data.azurerm_client_config.current.tenant_id
  client_id     = azuread_application.this.client_id
  client_secret = azuread_application_password.this.value
  # Workspace Folder resources/data sources (fabric_folder, fabric_folders)
  # are preview-only as of provider 1.13.0 - required to place lkh_001 into
  # data_engineering/lakehouses (see fabric_lakehouse.tf).
  preview = true
}
