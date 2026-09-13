locals {
  name_prefix = "northstar-${var.customer_id}-${var.environment}"

  # Storage account names must be globally unique, lowercase alphanumeric,
  # <=24 chars - no room for a readable prefix + random suffix both, so keep
  # it short and lean on the random suffix for uniqueness.
  storage_account_name = substr(
    lower(replace("st${var.customer_id}${var.environment}${random_string.suffix.result}", "-", "")),
    0, 24
  )

  merged_tags = merge(var.tags, {
    customer    = var.customer_id
    environment = var.environment
  })
}

resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

resource "azurerm_resource_group" "this" {
  name     = "rg-${local.name_prefix}"
  location = var.location
  tags     = local.merged_tags
}
