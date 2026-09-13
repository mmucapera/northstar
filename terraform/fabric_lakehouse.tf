# The Lakehouse northstar-formation's generated notebooks/pipelines target. Name
# must be exactly "lkh_001" - it's hardcoded throughout the build tooling
# (every `northstar-formation transform --generate-notebooks lkh_001 ...` call in
# northstar-formation/scripts/build_all_customers.sh, and every generated notebook
# references it directly).
#
# Schemas MUST be enabled: every generated table reference in this project is
# schema-qualified (bronze.reconciliation, silver.dim_partner,
# gold.fact_reconciliation, ...) - a non-schema-enabled Lakehouse would put
# every table flat under Tables/ with no bronze/silver/gold separation, and
# the generated DDL notebook's `CREATE SCHEMA IF NOT EXISTS bronze;` cells
# would fail outright.

# fabric-cicd mirrors northstar-deploy's repo folder structure into real Fabric
# workspace folders on every publish (auth/, data_modelling/semantic_models/,
# data_engineering/{notebooks,pipelines,demo_data}/, ...) - this is automatic,
# not something Terraform manages. The Lakehouse is the one exception: it's
# Terraform-owned (not fabric-cicd-managed, to avoid orphan-deletion risk -
# see docs/fabric-environment-setup-log.md), so it doesn't get swept into that
# mirroring and needs its own folder placement here, referencing the
# data_engineering folder fabric-cicd already created rather than creating a
# second one.
#
# Bootstrapping note: this data source only finds a "data_engineering" folder
# after at least one northstar-deploy publish has run for this customer. For a
# brand-new customer, deploy code first, then apply this.
data "fabric_folders" "all" {
  workspace_id = fabric_workspace.this.id
}

locals {
  data_engineering_folder_id = one([
    for f in data.fabric_folders.all.values : f.id
    if f.display_name == "data_engineering" && f.parent_folder_id == null
  ])
}

resource "fabric_folder" "lakehouses" {
  display_name     = "lakehouses"
  workspace_id     = fabric_workspace.this.id
  parent_folder_id = local.data_engineering_folder_id
}

resource "fabric_lakehouse" "lkh_001" {
  display_name = "lkh_001"
  workspace_id = fabric_workspace.this.id
  description  = "Northstar ${var.customer_id} pilot - bronze/silver/gold medallion lakehouse."
  folder_id    = fabric_folder.lakehouses.id

  configuration = {
    enable_schemas = true
  }
}
