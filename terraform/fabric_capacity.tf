# Microsoft Fabric capacity - the thing this whole module exists to create.
# F2 by default: smallest paid SKU, cheap, and can be paused between demo
# sessions (paused capacity costs nothing). Bump to F64 to match the
# production template default once this moves past demo/pilot
# (northstar-deploy/configurations/_templates/customer-template/parameters/prod.yml).
#
# Capacity name must be globally unique, lowercase alphanumeric, 3-63 chars.

resource "azurerm_fabric_capacity" "this" {
  name                = substr(lower(replace("fc${var.customer_id}${var.environment}${random_string.suffix.result}", "-", "")), 0, 63)
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location

  administration_members = var.admin_object_ids

  sku {
    name = var.capacity_sku
    tier = "Fabric"
  }

  tags = local.merged_tags
}
