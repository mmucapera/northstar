terraform {
  required_version = ">= 1.7.0"

  required_providers {
    azurerm = {
      source = "hashicorp/azurerm"
      # azurerm_fabric_capacity is a 4.x-era resource. `terraform init` will
      # pull the latest 4.x - if `plan` reports an unknown resource type,
      # you're on an older cached provider; run `terraform init -upgrade`.
      version = "~> 4.0"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    fabric = {
      source  = "microsoft/fabric"
      version = ">= 1.0.0"
    }
  }
}
