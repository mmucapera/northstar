# Northstar pilot infrastructure

Provisions the infrastructure for a Northstar customer pilot: resource group, ADLS Gen2
storage, Key Vault, a Fabric capacity, a Fabric workspace assigned to it, the `lkh_001`
Lakehouse every `northstar-formation` build targets, and the Service Principal that
`northstar-deploy`/`northstar-flow` authenticate with.

**Scope note:** this module creates the workspace and the empty Lakehouse shell itself, but
does **not** populate anything inside the Lakehouse (tables, schemas beyond the enabled
feature flag) or deploy notebooks/pipelines — `northstar-deploy`'s existing `fabric-cicd`-based
tooling already does that job well; duplicating it here would mean two tools fighting over the
same workspace contents. See `next_steps` output after `apply` for exactly what to do once this
module finishes.

## What this creates

| Resource | Purpose |
|---|---|
| Resource group | Container for everything below |
| Storage account (ADLS Gen2) + `extracts` container | Lands customer extract files, matches `northstar-flow`'s ADLS poller |
| Key Vault (RBAC) | Holds the SPN client secret |
| Fabric capacity (F2 by default) | The compute Fabric workspaces run on |
| Fabric workspace | Assigned to the capacity above (or an existing trial capacity — see `capacity_display_name`) |
| Fabric Lakehouse (`lkh_001`, schemas enabled) | The Lakehouse every `northstar-formation` build targets by name — schemas must be on, since every generated table reference is schema-qualified (`bronze.reconciliation`, `gold.fact_reconciliation`, etc.) |
| Entra app registration + Service Principal + client secret | Auth for `northstar-deploy/scripts/auth/auth_spn.py` — outputs map directly to its `TENANT_ID`/`CLIENT_ID`/`CLIENT_SECRET` env vars |

## Cost

F2 is the smallest paid Fabric SKU — roughly **$262/month if left running continuously**, but
Fabric capacity can be **paused** when not in active use, which stops billing entirely. Storage
and Key Vault costs are negligible at this scale (well under $5/month).

**While this pilot is in demo mode, the capacity is intentionally left paused by default** and
should only be resumed when the team needs to refresh/update data in the Lakehouse, then paused
again afterward. Left running, it accrues cost 24/7 regardless of actual usage — this is exactly
what happened during initial setup (the capacity ran continuously for several days before anyone
noticed the cost). Use the helper script rather than remembering the raw Azure CLI/portal steps:

```bash
terraform/scripts/fabric_capacity.sh status   # check current state
terraform/scripts/fabric_capacity.sh resume   # before a data refresh / demo session
terraform/scripts/fabric_capacity.sh pause    # afterward - do this every time
```

(Needs `terraform output` to work, i.e. state must be initialized in this directory. The Fabric
portal → capacity → Pause/Resume buttons work identically if you prefer the UI.)

There's no scheduled auto-pause yet — pausing is a manual step (or a script call) after each
session. A scheduled runbook (e.g. Azure Automation, pause outside business hours) would remove
the need to remember this, but hasn't been built — worth adding if manual pausing keeps getting
missed.

**Prefer the 60-day Fabric trial over this if you just need to demo something soon** — it's
free and doesn't need any of this. This module is for when you need infrastructure that
outlives a trial, or need it provisioned reproducibly (e.g. a second customer later).

## Prerequisites

1. An Azure subscription, and `az login` completed locally.
2. **Sign into https://app.fabric.microsoft.com at least once**, with a genuine native Entra
   user — *not* the personal Microsoft account that created the subscription, even if that
   account technically works for `az login`/Azure Resource Manager. Fabric's own sign-in page
   rejects personal accounts outright ("You can't sign in here with a personal account"), and
   on a brand-new tenant Fabric has no "home region" registered until a real work/school user
   visits the Fabric or Power BI web app once. If your tenant was created with a personal
   account, create a native user first: Entra admin center → Users → **Create new user** (not
   "Invite external user" — that produces a `#EXT#`-suffixed guest object Fabric also rejects).
   Hit both of these exact things setting up the CUSTOMER0 pilot — see
   `docs/fabric-environment-setup-log.md` for the full trail. Signing into the 60-day Fabric
   trial as that native user also satisfies this, if you want to do that anyway.
3. **A tenant Fabric admin (the native user above) must enable "Service principals can use
   Fabric APIs"** in the Fabric Admin Portal, scoped to this module's SPN or a security group
   containing it, *before* `terraform apply` will succeed on the `fabric_workspace` resource —
   Terraform/the API cannot do this step itself, and the `fabric` provider authenticates as
   that SPN (see `providers.tf`), not as whichever account ran `az login`.
4. Your own Entra object ID for `admin_object_ids`:
   ```
   az ad signed-in-user show --query id -o tsv
   ```
5. Terraform >= 1.7.
6. **Register the `Microsoft.Fabric` resource provider before your first `apply`**, especially
   on a brand-new subscription — it's usually not pre-registered, and `azurerm_fabric_capacity`
   fails with a 409 `MissingSubscriptionRegistration` error otherwise (hit this exact thing
   setting up the CUSTOMER0 pilot — see `docs/fabric-environment-setup-log.md`):
   ```bash
   az provider register --namespace Microsoft.Fabric
   # registration is async - poll until it's done:
   az provider show --namespace Microsoft.Fabric --query registrationState -o tsv
   ```

## Usage

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars: at minimum, set admin_object_ids to your own object ID

terraform init
terraform plan    # review before applying - this creates real, billed resources
terraform apply
```

After `apply`, read the `next_steps` output — it lists exactly which `northstar-deploy` config files
to fill in with the outputs.

To get the client secret (not shown in plaintext by default):
```bash
terraform output -raw spn_client_secret
```

### Using the free trial capacity instead of (or before) the paid F2

If the F2 quota request is still pending, or you just want to avoid the cost, point the
workspace at an existing Fabric trial capacity instead — set `capacity_display_name` in
`terraform.tfvars` to whatever the trial capacity is actually named in the Fabric Admin Portal's
capacity list (there's no reliable way to guess this name, check the portal). Leave it unset
(the default) to use the Terraform-managed paid F2 capacity. Switching between the two later is
a capacity reassignment on the existing workspace, not a recreate.

## Tearing down

```bash
terraform destroy
```

This deletes the Fabric capacity, storage account, Key Vault, and SPN. It does **not** delete
anything inside a Fabric workspace assigned to this capacity — detach or delete the workspace
first via the Fabric portal, or `destroy` will fail with the capacity still in use.

## Re-running for a second customer

This module is parameterized by `customer_id`/`environment`, matching the
`northstar-deploy/configurations/<customer>/` pattern. For Prospect A or Prospect B, use a separate
Terraform state (a new working directory or workspace with its own `terraform.tfvars`) rather
than changing `customer_id` in place — otherwise Terraform will try to rename/replace the
existing pilot's resources instead of creating new ones alongside it.
