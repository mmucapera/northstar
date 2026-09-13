# Fabric workspace - the thing northstar-deploy's fabric-cicd tooling deploys
# Lakehouse/notebooks/pipelines into. This module still doesn't manage those
# items (see README "Scope note") - just the empty workspace + capacity
# assignment.
#
# capacity_display_name lets this workspace run on the free 60-day Fabric
# trial capacity (tenant-native, not an Azure resource, not blocked by the
# Azure regional quota that blocked the paid F2 - see
# docs/fabric-environment-setup-log.md) while the F2 quota request is
# pending. Once F2 exists, unset capacity_display_name (leave it null) to
# switch this workspace onto the Terraform-managed azurerm_fabric_capacity
# instead - that's a capacity reassignment, not a workspace recreate.

variable "capacity_display_name" {
  description = <<-EOT
    Display name of an EXISTING Fabric capacity to assign the workspace to
    (e.g. the tenant's trial capacity - check the exact name in the Fabric
    Admin Portal's capacity list, it's not something this module can guess).
    Leave null (the default) to use the Terraform-managed paid capacity
    (azurerm_fabric_capacity.this) instead.
  EOT
  type        = string
  default     = null
}

data "fabric_capacity" "existing" {
  count        = var.capacity_display_name != null ? 1 : 0
  display_name = var.capacity_display_name

  lifecycle {
    postcondition {
      condition     = self.state == "Active"
      error_message = "Capacity '${var.capacity_display_name}' is not Active - check the Fabric Admin Portal."
    }
  }
}

data "fabric_capacity" "managed" {
  count        = var.capacity_display_name == null ? 1 : 0
  display_name = azurerm_fabric_capacity.this.name
}

locals {
  workspace_capacity_id = var.capacity_display_name != null ? data.fabric_capacity.existing[0].id : data.fabric_capacity.managed[0].id
}

resource "fabric_workspace" "this" {
  display_name = "${var.customer_id}-${var.environment}"
  description  = "Northstar ${var.customer_id} pilot - pre-discovery, synthetic data (see docs/customer0-pilot-kickoff.md)."
  capacity_id  = local.workspace_capacity_id
}

# By default the SPN that creates this workspace is its ONLY member - no
# human can even see it exists in the Fabric portal (hit this exact thing
# setting up the CUSTOMER0 pilot - see docs/fabric-environment-setup-log.md).
# Grant every admin_object_ids entry Admin on the workspace too. Note the
# format mismatch with admin_object_ids' other use (azurerm_fabric_capacity's
# administration_members wants UPN-for-users) - workspace role assignment
# wants an actual object ID for users, not a UPN, so user entries need a
# lookup here first.
locals {
  admin_user_upns = [for a in var.admin_object_ids : a if strcontains(a, "@")]
  admin_spn_ids   = [for a in var.admin_object_ids : a if !strcontains(a, "@")]
}

data "azuread_user" "admins" {
  for_each            = toset(local.admin_user_upns)
  user_principal_name = each.value
}

resource "fabric_workspace_role_assignment" "admin_users" {
  for_each     = data.azuread_user.admins
  workspace_id = fabric_workspace.this.id
  principal = {
    id   = each.value.object_id
    type = "User"
  }
  role = "Admin"
}

resource "fabric_workspace_role_assignment" "admin_spns" {
  for_each     = toset(local.admin_spn_ids)
  workspace_id = fabric_workspace.this.id
  principal = {
    id   = each.value
    type = "ServicePrincipal"
  }
  role = "Admin"
}
