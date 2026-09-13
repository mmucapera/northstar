variable "customer_id" {
  description = "Customer slug, matching northstar-deploy/configurations/<customer_id> and northstar-formation/models/customers/<customer_id>."
  type        = string
  default     = "customer0"
}

variable "environment" {
  description = "Environment name (dev/test/uat/prod), matching northstar-deploy's parameter file naming."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "test", "uat", "prod"], var.environment)
    error_message = "environment must be one of: dev, test, uat, prod."
  }
}

variable "location" {
  description = <<-EOT
    Azure region. Defaults to West Europe, which definitely supports Fabric
    capacity. If data residency in Africa matters for the real deployment,
    check whether Fabric capacity is available in South Africa North first -
    it's not guaranteed for every Azure service, and this default is
    deliberately the safe, always-supported choice rather than a guess.
  EOT
  type        = string
  default     = "westeurope"
}

variable "capacity_sku" {
  description = "Fabric capacity SKU. F2 is the smallest paid tier - cheap to run, pausable between demo sessions. Use F64 for the real production template default (see northstar-deploy/configurations/_templates/customer-template/parameters/prod.yml)."
  type        = string
  default     = "F2"
}

variable "admin_object_ids" {
  description = <<-EOT
    Fabric capacity administrators - format matters and the Fabric API is
    strict about it, confirmed the hard way setting up the CUSTOMER0 pilot (see
    docs/fabric-environment-setup-log.md):
      - Entra USER -> UPN string, e.g. "user@yourtenant.onmicrosoft.com"
        (an object ID for a user fails with "All provided principals must be
        existing, user or service principals", even for a real, valid user)
      - Service principal -> object ID (GUID)
    If your tenant was created by signing up for Azure with a personal
    Microsoft account, do NOT use that account here even if it appears in
    `az ad user list` - it shows up with a `#EXT#`-suffixed UPN (an
    external/guest-style representation) and Fabric rejects it outright.
    Create a genuine native user first (Entra admin center -> Users ->
    "Create new user", not "Invite external user") and use that user's UPN.
  EOT
  type        = list(string)

  validation {
    condition     = length(var.admin_object_ids) > 0
    error_message = "admin_object_ids must contain at least one Entra object ID or UPN - Fabric capacity requires at least one administrator."
  }
}

variable "tags" {
  description = "Tags applied to every resource this module creates."
  type        = map(string)
  default = {
    project    = "northstar"
    managed_by = "terraform"
    purpose    = "pilot-demo"
  }
}

variable "groq_api_key" {
  description = "Groq API key for the webapp's AI assistant (console.groq.com) - a placeholder for Anthropic until billing is set up there (see frontend/src/data/assistant.ts). Stored in Key Vault, referenced by the App Service, never in state as a bare app-setting value."
  type        = string
  sensitive   = true
}
