# Service Principal for Fabric API auth - matches exactly what
# northstar-deploy/scripts/auth/auth_spn.py expects: TENANT_ID/CLIENT_ID/
# CLIENT_SECRET env vars, client_credentials grant against
# https://api.fabric.microsoft.com/.default. That script only handles token
# acquisition - it does NOT grant Fabric API access. Before this SPN can
# actually call the Fabric API, a tenant Fabric admin must enable
# "Service principals can use Fabric APIs" in the Fabric Admin Portal for
# this SPN (or its security group) - that's a manual, one-time, tenant-admin
# action with no API/Terraform equivalent. Do this before assigning the SPN
# to any Fabric workspace.

resource "azuread_application" "this" {
  display_name = "northstar-${var.customer_id}-${var.environment}-spn"
  owners       = [data.azurerm_client_config.current.object_id]

  tags = ["northstar", var.customer_id, var.environment]
}

resource "azuread_service_principal" "this" {
  client_id                    = azuread_application.this.client_id
  app_role_assignment_required = false
  owners                       = [data.azurerm_client_config.current.object_id]

  tags = ["northstar", var.customer_id, var.environment]
}

resource "azuread_application_password" "this" {
  application_id = azuread_application.this.id
  display_name   = "terraform-managed"
  end_date       = timeadd(timestamp(), "8760h") # 1 year - rotate before this expires

  # timestamp() re-evaluates every plan; without this, end_date would drift
  # by a few seconds each run and Terraform would want to replace the
  # password every time. Pin it to the value set at creation instead.
  lifecycle {
    ignore_changes = [end_date]
  }
}
