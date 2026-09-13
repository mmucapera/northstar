# Fabric environment setup — command log

Running log of every command used to set up the Azure/Fabric environment for the CUSTOMER0 pilot,
in order, with real output. Kept so the setup is reproducible for a second customer later
(Prospect A/Prospect B) and so anyone picking this up mid-way can see exactly what state things
are in. Append to this file as we go — don't summarize old entries away.

Account: `marcosmucapera@hotmail.com` (personal Microsoft account; Azure auto-created a default
Entra ID tenant on signup — `marcosmucaperahotmail.onmicrosoft.com`, tenant ID
`da7b5aef-13f8-42f1-8e76-c3908c190d07`). Subscription: `subscription-dev`
(`ef02c3c4-1a70-42e6-9461-e1e0a33df213`).

## 2026-09-06

**Signed in:**
```bash
az login
```
Opened a browser, signed in as `marcosmucapera@hotmail.com`. Succeeded.

**Checked subscription state:**
```bash
az account show -o json
```
```json
{
  "environmentName": "AzureCloud",
  "homeTenantId": "da7b5aef-13f8-42f1-8e76-c3908c190d07",
  "id": "ef02c3c4-1a70-42e6-9461-e1e0a33df213",
  "isDefault": true,
  "managedByTenants": [],
  "name": "subscription-dev",
  "state": "Disabled",
  "tenantDefaultDomain": "marcosmucaperahotmail.onmicrosoft.com",
  "tenantDisplayName": "Default Directory",
  "tenantId": "da7b5aef-13f8-42f1-8e76-c3908c190d07",
  "user": {
    "name": "marcosmucapera@hotmail.com",
    "type": "user"
  }
}
```
**Finding: subscription state = `Disabled`.** Nothing can be provisioned until this clears.

**Confirmed it's the only subscription, and disabled enough to be filtered by default:**
```bash
az account list -o table
```
```
WARNING: A few accounts are skipped as they don't have 'Enabled' state. Use '--all' to display them.
```
(empty table — zero enabled subscriptions)

**Diagnosis:** account-level billing/verification issue, not something the CLI or Terraform can
fix — needs resolution in the Azure Portal (Subscriptions blade) or a support ticket.

**User action (outside this session):** found a pending payment on the account, paid it. As of
this entry, reactivation is still processing on Azure's side — re-checked with the same
`az account show` command above at [time of this entry], state still `Disabled`. Waiting on
Azure to finish reactivating; re-check periodically with the same command, no new command needed.

**Re-checked after user paid and Azure finished reactivating:**
```bash
az account show -o json
```
Still showed `"state": "Disabled"` — this turned out to be a stale local CLI cache, not the
real state. Forced a refresh instead of re-logging-in:
```bash
az account list --refresh -o json
```
```json
[
  {
    "cloudName": "AzureCloud",
    "homeTenantId": "da7b5aef-13f8-42f1-8e76-c3908c190d07",
    "id": "ef02c3c4-1a70-42e6-9461-e1e0a33df213",
    "isDefault": true,
    "managedByTenants": [],
    "name": "subscription-dev",
    "state": "Enabled",
    "tenantDefaultDomain": "marcosmucaperahotmail.onmicrosoft.com",
    "tenantDisplayName": "Default Directory",
    "tenantId": "da7b5aef-13f8-42f1-8e76-c3908c190d07",
    "user": {
      "name": "marcosmucapera@hotmail.com",
      "type": "user"
    }
  }
]
```
**Subscription is now `Enabled`.** Lesson for next time (Prospect A/Prospect B setup): after
reactivating a subscription, use `az account list --refresh` rather than plain `az account
show`/`az account list` — the CLI caches subscription state locally and won't show a change
otherwise.

**Got the signed-in user's Entra object ID** (needed for `admin_object_ids` in
`terraform/terraform.tfvars` — Fabric capacity requires at least one administrator):
```bash
az ad signed-in-user show --query id -o tsv
```
```
61647b3d-7113-432e-9e3c-eb2f745bdcea
```

**Created `terraform/terraform.tfvars`** (gitignored, real values) with `customer_id = "customer0"`,
`environment = "dev"`, `location = "westeurope"`, `capacity_sku = "F2"`, and
`admin_object_ids = ["61647b3d-7113-432e-9e3c-eb2f745bdcea"]` (the object ID above). Confirmed
gitignored before writing anything real into it:
```bash
git check-ignore -v terraform.tfvars
```
```
terraform/.gitignore:11:*.tfvars	terraform.tfvars
```

**First `terraform init` attempt failed** — local Terraform was 1.5.7, below the `>= 1.7.0`
floor in `versions.tf` (kept that constraint as-is rather than weakening it):
```bash
cd terraform && terraform init
```
```
Error: Unsupported Terraform Core version
This configuration does not support Terraform version 1.5.7.
```

**Upgraded Terraform.** `brew upgrade terraform` reported "already installed" — turned out
Homebrew's `terraform` formula was removed from `homebrew-core` (HashiCorp pulled it over
licensing), so the cached 1.5.7 was stale and nothing newer was available from that tap.
Switched to HashiCorp's official tap:
```bash
brew tap hashicorp/tap
brew install hashicorp/tap/terraform
```
Failed once — can't have the same formula name installed from two taps at once:
```
Error: terraform was installed from the homebrew/core tap
but you are trying to install it from the hashicorp/tap tap.
```
Fixed:
```bash
brew uninstall terraform
brew install hashicorp/tap/terraform
```
Installed Terraform 1.16.0. Confirmed:
```bash
terraform version
```
```
Terraform v1.16.0
on darwin_arm64
```
**Lesson for next time:** if `terraform` was installed via plain `brew install terraform`
before, it's on the stale homebrew-core copy — always use `hashicorp/tap/terraform` instead.

**`terraform init` succeeded:**
```bash
terraform init
```
Installed `hashicorp/azuread v3.9.0`, `hashicorp/random v3.9.0`, `hashicorp/azurerm v4.81.0`,
wrote `.terraform.lock.hcl`.

**Fixed a mistake in `terraform/.gitignore`** while here: it excluded `.terraform.lock.hcl`,
which should actually be committed (pins exact provider versions/checksums — directly matters
for "reuse everything" reproducibility). Only `.terraform/` (the provider binary cache) and
`*.tfstate*` should be ignored. Fixed before this went any further.

**`terraform plan` succeeded against the real subscription** — 0 errors, confirms the whole
module resolves correctly now that the subscription is enabled:
```bash
terraform plan -out=tfplan
```
```
Plan: 13 to add, 0 to change, 0 to destroy.
```
13 resources, listed via:
```bash
terraform show -json tfplan | python3 -c "
import json, sys
data = json.load(sys.stdin)
for r in data['resource_changes']:
    print(f\"{r['type']}.{r['name']} -> {r['change']['actions']}\")
"
```
```
azuread_application.this -> ['create']
azuread_application_password.this -> ['create']
azuread_service_principal.this -> ['create']
azurerm_fabric_capacity.this -> ['create']
azurerm_key_vault.this -> ['create']
azurerm_key_vault_secret.spn_client_secret -> ['create']
azurerm_resource_group.this -> ['create']
azurerm_role_assignment.deployer_kv_admin -> ['create']
azurerm_role_assignment.spn_kv_secrets_officer -> ['create']
azurerm_role_assignment.spn_storage_contributor -> ['create']
azurerm_storage_account.this -> ['create']
azurerm_storage_container.extracts -> ['create']
random_string.suffix -> ['create']
```
Plan saved to `tfplan` — caught that this file wasn't actually covered by `.gitignore` yet
(binary plan files can contain sensitive values, same as state). Fixed:
```bash
git check-ignore -v tfplan   # exit 1 - not ignored, before the fix
```
Added `*.tfplan`, `tfplan`, `plan.out`, `*.plan` to `terraform/.gitignore`. Re-confirmed:
```bash
git check-ignore -v tfplan
```
```
terraform/.gitignore:9:tfplan	tfplan
```
**Not yet applied** — waiting on explicit go-ahead before creating real, billed resources.

**Applied.** User ran:
```bash
cd terraform
terraform apply "tfplan"
```
12 of 13 resources succeeded. The 13th (the actual Fabric capacity) failed:
```
Error: creating Capacity ...: unexpected status 409 (409 Conflict) with error:
MissingSubscriptionRegistration: The subscription is not registered to use namespace
'Microsoft.Fabric'. See https://aka.ms/rps-not-found for how to register subscriptions.
```
**Known, common gotcha on a fresh subscription** — resource providers aren't all pre-registered.
Fixed:
```bash
az provider show --namespace Microsoft.Fabric --query "registrationState" -o tsv
```
```
NotRegistered
```
```bash
az provider register --namespace Microsoft.Fabric
```
Registration is async — polled until it flipped to `Registered` (~60 seconds):
```bash
for i in $(seq 1 20); do
  state=$(az provider show --namespace Microsoft.Fabric --query "registrationState" -o tsv)
  echo "check $i: $state"
  [ "$state" = "Registered" ] && break
  sleep 6
done
```
```
check 1: Registering
...
check 10: Registered
```
**Lesson for next time (Prospect A/Prospect B setup):** register `Microsoft.Fabric` on a brand new
subscription *before* the first `terraform apply`, not after — would have avoided this partial
apply. Worth adding as an explicit step 0 in the README for future customers.

Confirmed what already landed from the partial apply before regenerating a plan for the rest:
```bash
terraform state list
```
```
data.azurerm_client_config.current
azuread_application.this
azuread_application_password.this
azuread_service_principal.this
azurerm_key_vault.this
azurerm_key_vault_secret.spn_client_secret
azurerm_resource_group.this
azurerm_role_assignment.deployer_kv_admin
azurerm_role_assignment.spn_kv_secrets_officer
azurerm_role_assignment.spn_storage_contributor
azurerm_storage_account.this
azurerm_storage_container.extracts
random_string.suffix
```
12 of 13 — only `azurerm_fabric_capacity.this` still missing. Re-planning to pick up just that.

**Re-planned and re-applied:**
```bash
terraform plan -out=tfplan
```
```
Plan: 1 to add, 0 to change, 0 to destroy.
```
```bash
terraform apply "tfplan"
```
Failed again, different error this time:
```
Error: creating Capacity ...: unexpected status 400 (400 Bad Request) with error:
BadRequest: Tenant 'MetadataLocator: [TenantId=da7b5aef-13f8-42f1-8e76-c3908c190d07, ...]'
wasn't recognized by Microsoft Fabric. Sign up for Microsoft Fabric and try again.
```
**Diagnosis:** this tenant has never had a Fabric/Power BI "home region" established — that
happens the first time any user in the tenant actually signs into the Fabric or Power BI web
app (`app.fabric.microsoft.com`), not automatically from an Azure subscription existing. The
Fabric capacity ARM API refuses to provision into a tenant it doesn't recognize yet. This is a
one-time browser action, not something the CLI or Terraform can trigger.

**User action needed (outside this session):** sign into https://app.fabric.microsoft.com with
`marcosmucapera@hotmail.com` at least once — this registers the tenant with Fabric. Then retry
`terraform apply "tfplan"` (the plan file is unchanged and still valid).

**Lesson for next time:** add "sign into app.fabric.microsoft.com once, with the same account
that will run Terraform" as an explicit prerequisite step in the README, before `terraform
apply` is ever attempted — would have caught this before the first failed apply, not the second.

**Attempted the sign-in — hit a further, more fundamental blocker:**
`app.fabric.microsoft.com` rejected `marcosmucapera@hotmail.com` outright: *"You can't sign in
here with a personal account. Use your work or school account instead."*

**Diagnosis:** a personal Microsoft account (MSA) used to create an Azure subscription gets
linked to the auto-created default directory well enough for Azure Resource Manager (`az login`,
Terraform's ARM-level resources — resource group/storage/Key Vault all succeeded on this
identity) but is *not* a real Entra ID "work or school" user object. Fabric's own sign-in page
checks for that distinction directly and refuses MSAs, even ones tied to a real tenant.

**Fix in progress:** create an actual Entra ID user inside the tenant
(`marcosmucaperahotmail.onmicrosoft.com`, confirmed default domain from `az account show`
earlier), assign Global Administrator, and sign into Fabric as *that* user instead of the MSA.
Steps given: Entra admin center → Users → New user → UPN
`admin@marcosmucaperahotmail.onmicrosoft.com` → assign Global Administrator → sign into
`app.fabric.microsoft.com` as that user in a private browser window (avoids session mixing with
the MSA login). Waiting on this before retrying `terraform apply "tfplan"`.

**Lesson for next time:** the real prerequisite for a personal-account-created subscription
isn't just "sign into Fabric once" — it's "create a real Entra ID user in the tenant first,
then sign into Fabric as that user." Update the README prerequisite once this is confirmed
working, not before (don't want to document an unverified fix).

**Confirmed fixed** — user created a native Entra ID user (not an "Invite external user" guest,
which is what the pre-existing `marcosmucapera_hotmail.com#EXT#@marcosmucaperahotmail.onmicrosoft.com`
object was — that `#EXT#` suffix is exactly what identifies an external/personal-account
representation, same one Fabric had already rejected, not a usable alternative) and signed into
Fabric as that new user. Fabric now recognizes the tenant. Retrying `terraform apply "tfplan"`
next. README prerequisite update (see below) is now confirmed, not speculative.

**Retried `terraform apply "tfplan"` — two more issues, back to back:**

1. `Error: Saved plan is stale` — state had moved on since the plan was saved (from the earlier
   failed attempts). Fixed by just regenerating: `terraform plan -out=tfplan` (still only
   `Plan: 1 to add` — the Fabric capacity), then `terraform apply "tfplan"` again.

2. New error from the Fabric API itself:
   ```
   Error: creating Capacity ...: unexpected status 400 (400 Bad Request) with error:
   BadRequest: All provided principals must be existing, user or service principals
   ```
   **Diagnosis:** `admin_object_ids` still pointed at the MSA's object ID
   (`61647b3d-7113-432e-9e3c-eb2f745bdcea`) — the same `#EXT#`-suffixed external/guest-style
   object that Fabric's sign-in page already rejected. Fabric capacity's
   `administration_members` won't accept it either, for the same underlying reason.

   **Fixed:** found the native user created earlier via:
   ```bash
   az ad user list --query "[].{upn:userPrincipalName, id:id, displayName:displayName}" -o table
   ```
   ```
   Upn                                                                    DisplayName
   ---------------------------------------------------------------------  ---------------
   marcosmucapera_hotmail.com#EXT#@marcosmucaperahotmail.onmicrosoft.com  Marcos Mucapera
   mmucapera@marcosmucaperahotmail.onmicrosoft.com                        Mucapera
   ```
   Got its object ID:
   ```bash
   az ad user show --id "mmucapera@marcosmucaperahotmail.onmicrosoft.com" --query id -o tsv
   ```
   ```
   73bd6f10-494c-49ab-96b3-2352298da716
   ```
   Replaced (not added alongside — the invalid entry would just fail the whole call again) the
   `admin_object_ids` entry in `terraform.tfvars` with this native user's object ID. Documented
   this whole gotcha in `terraform.tfvars.example` for the next customer setup.

Re-planning and re-applying next with the corrected `admin_object_ids`.

**Re-applied — principal error gone, confirming the UPN fix worked, but a new blocker:**
```bash
terraform plan -out=tfplan   # still Plan: 1 to add
terraform apply "tfplan"
```
```
Error: creating Capacity ...: unexpected status 400 (400 Bad Request) with error:
BadRequest: The sum total of CapacityUnits of all Fabric capacities in the current
subscription must not exceed the regional quota for the subscription! TotalCapacityUnits: 0,
RegionalQuota: 0, RequestedSku: F2.
```
**Diagnosis:** this subscription's Fabric capacity quota in West Europe is 0 — normal for a
brand-new subscription, not specific to anything done wrong here.

**Tried to check/fix via CLI first** (the `az quota` extension, which fronts a general Azure
quota API that in principle covers Fabric):
```bash
az extension add --name quota
az quota list --scope "/subscriptions/ef02c3c4-1a70-42e6-9461-e1e0a33df213/providers/Microsoft.Fabric/locations/westeurope"
```
```
ERROR: (MissingRegistrationForResourceProvider) The subscription is not in registered state
for the resource provider: Microsoft.Quota.
```
Registered it the same way as `Microsoft.Fabric` earlier:
```bash
az provider register --namespace Microsoft.Quota
# polled until Registered, ~66 seconds
az provider show --namespace Microsoft.Quota --query registrationState -o tsv   # confirmed: Registered
```
Retried `az quota list` (even after a 15s propagation wait) — **same error, still complaining
about `Microsoft.Quota` not being registered, despite `az provider show` confirming it is.**
Didn't chase this further — looks like a quirk in the `az quota` CLI extension itself rather
than a real registration problem, and the documented, reliable path is the Azure Portal's
Quotas page anyway. Moving to that instead of debugging the CLI extension.

**Next: user needs to request an F2 (or higher) Fabric capacity quota increase via the Azure
Portal** — Portal → search "Quotas" → Microsoft Fabric → find West Europe → New Quota Request
(or Help + Support → New support request → Service and subscription limits (quotas) → Microsoft
Fabric if the Quotas page doesn't offer self-service for this account). Per Microsoft's docs,
quota requests don't cost anything by themselves — only actual capacities are billed. Waiting
on this before retrying `terraform apply "tfplan"` again (plan itself needs no changes).

**Direct link used to navigate straight to the Quotas page (verified via Microsoft's own
docs before sending, not guessed):**
```
https://portal.azure.com/#view/Microsoft_Azure_Capacity/QuotaMenuBlade/~/myQuotas
```
Landed there fine on the personal account (`marcosmucapera@hotmail.com`) — confirms this page
isn't Fabric-branded and doesn't apply the same personal-account block as
`app.fabric.microsoft.com` or the Azure Portal's "Microsoft Fabric" resource-creation blade did
earlier. Had to change the page's **Provider** filter from its default "Compute" to
"Microsoft Fabric" to actually see the relevant quota (found: `CapacityQuota`, West Europe,
`subscription-dev`, 0 of 0).

Submitted a self-service request via the pencil/edit icon on that row, new limit = **2** (exact
minimum for F2 — user chose 2 over the 4 I'd suggested, which just means a follow-up request
later if F4 is ever wanted; fine either way). First attempt typed "F2" into the New limit field
— rejected, field wants a plain number (capacity units), not the SKU label. Corrected to "2"
and resubmitted.

**Self-service auto-approval failed:** *"We were unable to adjust your quota. Submit a support
ticket so that a support engineer can assist you..."* — normal for a brand-new subscription;
instant self-service approval isn't always available. Portal offered a **"Create a support
request"** button directly from that failure screen. Proceeding via that — this is now a
genuine wait on a Microsoft support engineer, not something fixable from the CLI or Terraform
side. Per Microsoft's docs, quota-only support requests are typically free and don't need a
paid support plan.

**Pivot while the quota ticket is pending: added Fabric workspace creation to Terraform.**
Realized the paid-F2 quota block doesn't need to stop all progress — the free 60-day Fabric
trial capacity is tenant-native, not an Azure ARM resource, so it isn't subject to the Azure
regional quota that blocked F2. Added:
- `microsoft/fabric` provider (`versions.tf`, pulled `v1.13.0` via `terraform init`)
- `provider "fabric"` block (`providers.tf`) authenticating as the SPN this module already
  creates, not whichever account ran `az login` — Fabric rejects personal accounts regardless
  of which tool is calling it, confirmed earlier both at `app.fabric.microsoft.com` and the
  Azure Portal's Fabric capacity blade
- `fabric_workspace.tf` — new `capacity_display_name` variable (optional; set to run the
  workspace on an existing named capacity like the trial, leave null for the Terraform-managed
  paid F2), a `fabric_capacity` data source lookup for that case, and the `fabric_workspace`
  resource itself
- `workspace_id` output, simplified `next_steps` (workspace creation is automated now)

`terraform init` + `terraform validate` both clean, zero warnings. **Not yet planned/applied**
— two things still needed first: (1) confirm the SPN's "Service principals can use Fabric APIs"
toggle is enabled in the Fabric Admin Portal (prerequisite for the `fabric` provider itself to
authenticate at all, independent of which capacity the workspace uses), (2) if using the trial
capacity, its exact display name from the Fabric Admin Portal's capacity list (no reliable way
to guess it) - set via `capacity_display_name` in `terraform.tfvars`.

**User checked Fabric Admin Portal → Tenant settings → Developer settings.** Found:
- "Service principals can call Fabric public APIs" — already **Enabled** for the entire org
- "Service principals can create workspaces, connections, and deployment pipelines" — **Disabled**
  (flagged this needs enabling too, specifically for workspace creation - separate from general
  API access)

**Found the trial capacity name** via Admin Portal → Capacity settings → Trial tab:
```
Trial-20260906T154818Z-JmZdt61IlESMnqaDCwkPaQ
```
Set in `terraform.tfvars`: `capacity_display_name = "Trial-20260906T154818Z-JmZdt61IlESMnqaDCwkPaQ"`.

**Ran `terraform plan -out=tfplan` then `terraform apply "tfplan"`.** Two outcomes:

1. **`azurerm_fabric_capacity.this` succeeded** — `Creation complete after 15s`. The F2 quota
   must have cleared (support ticket resolved faster than the portal's earlier "unable to
   adjust" message suggested, or it landed asynchronously). **The paid F2 capacity now exists**
   at `/subscriptions/ef02c3c4-.../resourceGroups/rg-northstar-customer0-dev/providers/Microsoft.Fabric/capacities/fccustomer0devri7hdc`.

2. **`fabric_workspace.this` failed:**
   ```
   Error: Create operation
   Could not create resource: The caller is not authenticated to access this resource
   Error Code: Unauthorized
   ```
   **Diagnosis:** exactly the gap flagged above — "can call Fabric public APIs" being enabled
   isn't sufficient for workspace creation specifically; that needs the separate
   "Service principals can create workspaces, connections, and deployment pipelines" toggle,
   which was still Disabled. Waiting on user to enable it, then retry `terraform apply "tfplan"`
   (only `fabric_workspace.this` remains — the capacity is already in state).

**Added Lakehouse creation to Terraform** (`fabric_lakehouse.tf`), while the SPN-toggle fix was
pending — a new `fabric_lakehouse` resource named exactly `lkh_001` (hardcoded throughout every
`northstar-formation` build already — see `northstar-formation/scripts/build_all_customers.sh`'s
`--generate-notebooks lkh_001` calls), with `configuration = { enable_schemas = true }`. Schemas
are mandatory, not optional, here — every generated table reference in this project is
schema-qualified (`bronze.reconciliation`, `gold.fact_reconciliation`, etc.) and the generated
DDL notebook's `CREATE SCHEMA IF NOT EXISTS bronze;` cells would fail on a non-schema-enabled
Lakehouse. Added a `lakehouse_id` output. `terraform init`/`validate`/`fmt` all clean.

**Retried `terraform plan -out=tfplan` + `terraform apply "tfplan"` after user reported enabling
the toggle.** Plan was clean (`fabric_lakehouse.lkh_001` + `fabric_workspace.this`, 2 to add —
capacity already in state from before). Apply still failed on the exact same error:
```
Error: Create operation
Could not create resource: The caller is not authenticated to access this resource
Error Code: Unauthorized
```
`fabric_lakehouse.lkh_001` wasn't attempted at all (correctly skipped - it depends on
`fabric_workspace.this.id`, which never got created).

**Diagnosis, not yet confirmed:** either (a) the toggle didn't actually get saved/enabled, (b)
it was enabled scoped to a specific security group that doesn't include this SPN rather than
"the entire organization", or (c) — matching a pattern hit twice already in this exact setup
(`Microsoft.Fabric` and `Microsoft.Quota` provider registration both needed ~60s before actually
taking effect despite showing "Registered" immediately) — this tenant setting also needs
propagation time before it's real. Asked user to re-verify the toggle's actual state in the
portal (not just "I clicked it") before retrying again.

**Confirmed and retried.** Same stale-plan issue as before (state moved between plan and apply
attempts) — regenerated with `terraform plan -out=tfplan`, then `terraform apply "tfplan"`.
**Both resources succeeded this time:**
```
fabric_workspace.this: Creation complete after 15s [id=2349db9d-a206-41d6-bb9b-c134bee74ee0]
fabric_lakehouse.lkh_001: Creation complete after 36s [id=f7dd2f1b-a528-4ea1-8169-ac6802c2594e]

Apply complete! Resources: 2 added, 0 changed, 0 destroyed.
```
So it really was the propagation-delay pattern (or the toggle needed a moment after being
re-confirmed) — not a scope/config problem after all.

## Environment complete (2026-09-06)

Everything the CUSTOMER0 pilot needs now exists for real, entirely via Terraform, in
`rg-northstar-customer0-dev` / West Europe:

| Thing | Value |
|---|---|
| Resource group | `rg-northstar-customer0-dev` |
| Storage account | `stcustomer0devri7hdc` (container: `extracts`) |
| Key Vault | `https://kv-northstar-customer0-dev.vault.azure.net/` |
| Fabric capacity (F2, paid) | `fccustomer0devri7hdc` — exists, not currently used (workspace is on the trial capacity — see `capacity_display_name` in `terraform.tfvars`) |
| Fabric workspace | `customer0-dev`, id `2349db9d-a206-41d6-bb9b-c134bee74ee0` |
| Fabric Lakehouse | `lkh_001`, id `f7dd2f1b-a528-4ea1-8169-ac6802c2594e`, schemas enabled |
| SPN | `northstar-customer0-dev-spn`, client id `49b7caf6-51ec-409c-951f-396337324bd7`, tenant `da7b5aef-13f8-42f1-8e76-c3908c190d07`, secret in Key Vault (`customer0-spn-client-secret`) |

**Not yet done** (tracked as next steps): wire these real values into
`northstar-deploy/configurations/customer0/config.yml` and `parameters/dev.yml` (replacing the placeholder
GUIDs), and run `northstar-formation`'s notebook/pipeline generation against this real
workspace_id/lakehouse_id instead of the placeholder GUID used for local-only verification
earlier (see `docs/customer0-pilot-kickoff.md`).

## Workspace was invisible to the human user (2026-09-06)

User reported "I can't see the workspace created" in the Fabric portal. Verified directly
rather than guessed — got an SPN access token the same way `auth_spn.py` does and queried the
Fabric API:
```bash
TOKEN=$(curl -s -X POST "https://login.microsoftonline.com/${TENANT_ID}/oauth2/v2.0/token" \
  -d "grant_type=client_credentials" -d "client_id=${CLIENT_ID}" \
  -d "client_secret=${CLIENT_SECRET}" -d "scope=https://api.fabric.microsoft.com/.default" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
curl -s -H "Authorization: Bearer ${TOKEN}" \
  "https://api.fabric.microsoft.com/v1/workspaces/${WORKSPACE_ID}/roleAssignments"
```
Confirmed the workspace genuinely exists (`capacityAssignmentProgress: "Completed"`) but its
**only** role assignment was the SPN itself as Admin — no human had any access, which is exactly
why it was invisible in the portal.

**Fixed properly in Terraform, not with a one-off portal click** — added to
`fabric_workspace.tf`: every `admin_object_ids` entry now also gets Admin on the workspace.
Real complication: `admin_object_ids` mixes formats (UPN for users, object ID for SPNs — needed
for the *capacity*'s `administration_members`), but workspace role assignment wants an actual
object ID for users, not a UPN. Added a `strcontains(a, "@")` split plus an `azuread_user` data
source lookup to resolve UPNs to object IDs before creating the role assignment. Verified the
`azuread_user` data source's attribute name (`object_id`, not `id`) directly against the
installed provider schema before writing this, same as everything else tonight - via
`terraform providers schema -json`.

`terraform validate` clean, `terraform plan` correctly resolved the native user's UPN
(`mmucapera@marcosmucaperahotmail.onmicrosoft.com`) to object ID `73bd6f10-...`, matching what
was found manually earlier via `az ad user show`. Applied - 1 resource added. Re-ran the same
role-assignments API check to confirm rather than assume:
```json
{
  "value": [
    {"principal": {"displayName": "Mucapera", "type": "User", ...}, "role": "Admin"},
    {"principal": {"displayName": "northstar-customer0-dev-spn", "type": "ServicePrincipal", ...}, "role": "Admin"}
  ]
}
```
Both now have Admin. The workspace should be visible in the Fabric portal now for the native
user - not yet confirmed visually by the user, next thing to check.

## First real deployment attempt (2026-09-06)

Regenerated CUSTOMER0's build fresh, this time targeting the real lakehouse/workspace directly
instead of placeholder GUIDs:
```bash
cd northstar-formation
.venv/bin/northstar-formation transform models/customers/customer0 --base models/_base -o output_customer0/ENG/sql
.venv/bin/northstar-formation transform models/customers/customer0 --base models/_base -o output_customer0/ENG/ \
  --generate-notebooks lkh_001 \
  --lakehouse-id f7dd2f1b-a528-4ea1-8169-ac6802c2594e \
  --lakehouse-workspace-id 2349db9d-a206-41d6-bb9b-c134bee74ee0 \
  --config-version v1
.venv/bin/northstar-formation pipelines -m models/customers/customer0 -n output_customer0/ENG/notebooks \
  -p data_pipelines/customers/customer0 -o output_customer0/ENG/pipelines -w 2349db9d-a206-41d6-bb9b-c134bee74ee0
```

**Discovered `northstar-deploy` has three separate deployment code paths, not one:**
`deploy/deploy_cli.py` (an interactive multi-target launcher for a different, more complex
group/environment matrix - `GROUP_ORDER`/`runtime_target_builder.py` - doesn't match our simple
per-customer config), `deploy/deploy_fabric_eng.py` (lower-level, calls fabric-cicd's
`FabricWorkspace`/`publish_all_items` directly), and `scripts/deployment/deploy_orchestrator.py`
(Pydantic-validated, `--customer`/`--environment` CLI args matching our config.yml pattern
directly - used this one).

**Safety check before touching anything live:** confirmed via `fabric_cicd`'s own source
(installed locally, read `fabric_workspace.py` directly rather than guess) that
`repository_directory` is scanned recursively (`os.walk`), so nested `notebooks/{bronze,silver,gold}/`
+ `pipelines/` folders are all discovered fine without flattening. But `item_types_in_scope`
included `Lakehouse`, and `lkh_001` was created by Terraform, not by anything in this repo
folder - a real risk that orphan-cleanup could delete it. **Removed `Lakehouse` from both
`item_types_in_scope` and `deployment_sequence`** in `config.yml` before running anything -
Lakehouse stays Terraform-owned, this repo only adds content into it.

**Set up the deploy environment:** recreated `northstar-deploy/.venv` with Python 3.12 (the existing
one was 3.14, and `fabric-cicd` caps at `<3.14` - same class of issue as `northstar-formation`'s venv
earlier). Installed `pyyaml pydantic colorlog requests azure-identity fabric-cicd` (fabric-cicd
1.3.0).

**Copied generated content into a real `versions/` folder** (the template's
`repository_directory` convention, previously unpopulated for every customer including the real
ones): `northstar-deploy/configurations/customer0/versions/v1.0.0/{notebooks,pipelines}/` - CUSTOMER0's own
bronze/silver/gold notebooks + UTL library + DDL/validation notebooks, and just the 3 core
pipelines (`PL_BRONZE_CONFIG`/`PL_SILVER_CONFIG`/`PL_GOLD_CONFIG`). Deliberately excluded the
`00_PRE_ORCH`/`01_ORCH`/`DEMO_GENERATOR` shared pipelines copied from the generic `_c000`
template customer - unverified for CUSTOMER0's actual structure, not something to push into a live
workspace on a first attempt.

Set `config.yml`'s `workspace_id.dev` and `repository_directory.dev` to the real values.
Updated `parameters/dev.yml`'s `STORAGE_ACCOUNT`/`KEY_VAULT_URI` to real values too (though
confirmed via `grep -r '{{' versions/v1.0.0` that none of our generated content actually
contains `{{PLACEHOLDER}}` tokens - northstar-formation bakes in real IDs at generation time, so
fabric-cicd's find/replace step is a no-op here regardless).

**First deployment attempt:**
```bash
TENANT_ID=$(cd ../terraform && terraform output -raw spn_tenant_id) \
CLIENT_ID=$(cd ../terraform && terraform output -raw spn_client_id) \
CLIENT_SECRET=$(cd ../terraform && terraform output -raw spn_client_secret) \
  .venv/bin/python deploy.py --customer customer0 --environment dev --mode incremental
```
(`--mode incremental` chosen deliberately for this first run - `cleanup_orphans: false`, no
deletion risk, vs. `full` mode's `cleanup_orphans: true`.)

SPN authentication succeeded and found the workspace ("Connection successful. Found 1
accessible workspaces") - real confirmation the SPN can actually see and reach it. Failed on
config validation:
```
Configuration validation failed: 1 validation error for CustomerConfig
core.parameter
  Input should be a valid string [type=string_type, input_value={'dev': './parameters/dev...
```
**Diagnosis:** the `_templates/customer-template` shape for `core.parameter` (a per-env dict of
file paths) doesn't match `scripts/deployment/config_models.py`'s actual `CoreConfig` Pydantic
model, where `parameter: Optional[str] = None` - a single string or nothing, not a dict. This
orchestrator most likely expects the inline `parameter_replacements` structure instead (seen
earlier in the real `deploy-c/config.yml` example), not file-path references at all. Since we
already confirmed find/replace is a no-op for our content anyway, fixed by just **removing**
`core.parameter` from `config.yml` rather than reshaping it into something unused - `parameter`
is Optional, omitting it is valid.

**Retried - config validated fine this time, but a new failure**: pre-deployment's
`verify_dependencies` check failed with `Missing dependencies`. Read `validation.py` directly
rather than guess (`verify_dependencies`/`_check_dependency` in
`scripts/deployment/validation.py`): it walks `deployment_sequence` checking known dependency
pairs (`Report` depends on `SemanticModel`, `SemanticModel`/`Notebook`/`DataPipeline` depend on
`Lakehouse`, etc.) against what actually exists live in the workspace. Our scope included
`SemanticModel` and `Report` even though **CUSTOMER0 has zero generated content of either type** -
`northstar-formation` only ever produces Notebook/DataPipeline for this project, no Power BI semantic
models or reports exist at all. So the check correctly found "Report depends on SemanticModel"
unsatisfied, since neither was ever going to be deployed.

**Fixed by removing `SemanticModel`/`Report`** from both `item_types_in_scope` and
`deployment_sequence` - scoping the config to exactly what we actually generate and deploy
(`Notebook`, `DataPipeline`), rather than the template's generic four-type default.

**Retried - pre-deployment validation passed completely this time**, reached the actual
deployment step, and hit a real code bug (not a config issue):
```
TypeError: deploy_with_config() missing 1 required keyword-only argument: 'token_credential'
```
**Diagnosis:** `deploy_orchestrator.py`'s `_deploy_with_native_config()` calls `fabric_cicd`'s
`deploy_with_config(config_file_path=..., environment=...)` without a credential. Checked the
installed `fabric-cicd` 1.3.0 source directly (`publish.py`) - `token_credential` is a required
keyword-only argument, no default. The orchestrator already builds a `ClientSecretCredential`
earlier in `run()` (`self.credential`) and even passes it correctly in the *other*, unused
deployment code path (`_deploy_programmatically`) - just forgot to thread it through in the one
actually being called. Genuine, simple bug in this project's own code, not a fabric-cicd version
issue. **Fixed** with a one-line addition: `token_credential=self.credential` in the
`deploy_with_config()` call at `deploy_orchestrator.py` line ~577.

Retrying deployment next with the fix.

**Retried - `token_credential` fix worked (no more TypeError), new failure from `fabric-cicd`'s
own config validator** (a second, stricter validation layer beyond our internal Pydantic model):
```
ConfigValidationError: Configuration validation failed with 4 error(s):
  - 'workspace_id.prod' must be a valid GUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
  - 'workspace_id.test' must be a valid GUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
  - 'workspace_id.uat' must be a valid GUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
  - Configuration must specify either 'workspace_id' or 'workspace' in core section
```
**Diagnosis:** `fabric-cicd` validates *every listed environment's* `workspace_id` upfront, even
ones we're not deploying to right now - and the template's `xxxxxxxx-xxxx-...` placeholders for
test/uat/prod (which genuinely don't exist yet) fail its GUID format check outright. **Fixed by
removing test/uat/prod entirely** from both `workspace_id` and `repository_directory` rather
than faking valid-looking GUIDs - only `dev` is listed now, which is honest (that's the only
real workspace) and satisfies the validator (only requires `dev` to be present).

Retrying deployment next.

**Retried - GUID validation passed, hit a third real bug**, same class as the last two (this
orchestrator's own code, not a config mistake):
```
ConfigValidationError: Configuration validation failed with 1 error(s):
  - repository_directory not found at resolved path for environment 'dev':
    '/private/var/folders/.../T/versions/v1.0.0'
```
**Diagnosis:** `_deploy_with_native_config()` writes a temp config file under `/tmp` before
handing it to `fabric_cicd.deploy_with_config()`. `fabric-cicd` resolves relative
`repository_directory` paths *relative to the config file it's given* - which is now the temp
file's `/tmp` location, not our real `northstar-deploy/configurations/customer0/` directory. So
`"./versions/v1.0.0"` (the template default, a relative path) resolved to a nonexistent path
under `/tmp` instead of the real one. This would break for **every** customer using the
template's default relative `repository_directory` - not an customer0-specific issue.

**Fixed properly, not worked around** - patched `_deploy_with_native_config()` to rewrite any
relative `repository_directory` entries to absolute paths (resolved against
`self.config_path`, the orchestrator's already-tracked real config directory) before writing
the temp config file. Benefits every future customer, not just a one-off fix for customer0's config.

Retrying deployment next.

## First successful real deployment (2026-09-06)

Retried with the absolute-path fix. **Status: SUCCESS, 87/87 items, 54.57s.** Real content is
now live in the `customer0-dev` Fabric workspace:
- All 30 generated Notebooks (10 tables × bronze/silver/gold: `brz_reconciliation`,
  `slv_dim_partner`, `fact_hse_incidents`, etc.)
- All 3 core DataPipelines (`PL_BRONZE_CONFIG`, `PL_SILVER_CONFIG`, `PL_GOLD_CONFIG`)
- 54 shared UTL library notebooks (`nb_config_*` framework functions, DQ/validation tooling,
  audit/repair utilities) copied alongside

Confirmed via `fabric-cicd`'s own log output, not just the orchestrator's summary - each item
individually logged as `Publishing <Type> '<name>'` → `->Published <Type> '<name>'`.

**Four real bugs found and fixed along the way in `northstar-deploy`'s own code**, all general fixes
(not customer0-specific workarounds), benefiting every future customer deployment:
1. `deploy_with_config()` missing `token_credential` - `deploy_orchestrator.py` built a
   `ClientSecretCredential` but never threaded it through the code path actually being used.
2. `verify_dependencies` false-failing when `item_types_in_scope` includes a type with zero
   generated content (`SemanticModel`/`Report` for CUSTOMER0) - not itself a code bug, but a config
   footgun worth documenting (fixed by scoping config accurately, not by patching the checker).
3. Relative `repository_directory` paths resolving against the wrong directory once
   `_deploy_with_native_config()` copies the config into a `/tmp` temp file - fixed by
   resolving to absolute paths before the temp file is written.
4. (Config-only, not code) the template's per-env `xxxxxxxx-...` placeholder GUIDs for
   test/uat/prod fail `fabric-cicd`'s own stricter GUID validator even when only deploying to
   dev - fixed by omitting environments that don't exist yet rather than faking valid GUIDs.

**Full command sequence that worked, start to finish** (for replaying against Prospect A/Prospect B
later):
```bash
# 1. Generate content targeting the real workspace/lakehouse
cd northstar-formation
.venv/bin/northstar-formation transform models/customers/<customer> --base models/_base -o output_<customer>/ENG/sql
.venv/bin/northstar-formation transform models/customers/<customer> --base models/_base -o output_<customer>/ENG/ \
  --generate-notebooks lkh_001 --lakehouse-id <id> --lakehouse-workspace-id <id> --config-version v1
.venv/bin/northstar-formation pipelines -m models/customers/<customer> -n output_<customer>/ENG/notebooks \
  -p data_pipelines/customers/<customer> -o output_<customer>/ENG/pipelines -w <workspace-id>

# 2. Copy into a real versions/ folder (notebooks + the customer's own core pipelines only -
#    NOT the generic _c000 shared orchestration/demo pipelines, unverified for a new customer)
mkdir -p northstar-deploy/configurations/<customer>/versions/v1.0.0/{notebooks,pipelines}
cp -r output_<customer>/ENG/notebooks/* northstar-deploy/configurations/<customer>/versions/v1.0.0/notebooks/
cp -r output_<customer>/ENG/pipelines/PL_{BRONZE,SILVER,GOLD}_CONFIG.DataPipeline \
  northstar-deploy/configurations/<customer>/versions/v1.0.0/pipelines/

# 3. Deploy (item_types_in_scope = only what's actually generated; workspace_id/repository_directory
#    = only real environments, no placeholder GUIDs; core.parameter omitted)
cd ../northstar-deploy
TENANT_ID=... CLIENT_ID=... CLIENT_SECRET=... \
  .venv/bin/python deploy.py --customer <customer> --environment dev --mode incremental
```

---

## `auth/` folder: sibling deployment pattern (2026-09-06)

Added `northstar-formation/auth/` (4 notebooks — `nb_fetch_reports`, `nb_get_users`, `nb_auth`,
`nb_access_control` — plus `pl_auth.DataPipeline`) as source-controlled, customer-agnostic
content, converted from `.ipynb` to Fabric git format. Deployed alongside every customer's
generated `ENG/` output by hooking `copy_auth_files()` into `northstar-formation`'s CLI right after
`copy_library_notebooks()`. Per explicit correction, output lands at `output_<customer>/auth/`,
a **sibling** of `ENG/`, not nested inside it.

Two things worth remembering for the next customer:
- `pl_auth.DataPipeline`'s `notebookId` values must be each notebook's **logical ID** (from its
  own `.platform`), and `workspaceId` must be the `DEFAULT_GUID` placeholder
  (`00000000-0000-0000-0000-000000000000`) — `fabric-cicd`'s `_replace_logical_ids` resolves
  both to real IDs at publish time. Verified two ways: read `fabric-cicd`'s own source
  (`constants.DEFAULT_GUID`), then confirmed post-deploy via a direct `getDefinition` API call
  that the live pipeline shows real, resolved GUIDs.
- The pasted pipeline JSON originally had real foreign GUIDs baked in (from wherever it was
  exported) — would've silently broken on any workspace other than the one it came from. Always
  rewrite to logical-ID + DEFAULT_GUID before committing shared pipeline content.

## Synthetic daily bronze generator + pipeline chain (2026-09-06)

Built `nb_generate_dummy_bronze.Notebook` — a PySpark notebook that synthesizes realistic (not
"millions of rows" — demo-scale) FK-linked star-schema data directly into `bronze.*`, so the
**real** `PL_SILVER_CONFIG` → `PL_GOLD_CONFIG` pipelines run on top of it unmodified, rather than
writing a shortcut straight to gold. Covers all 10 CUSTOMER0 tables: `dim_partner`, `dim_field`,
`dim_period`, `dim_downtime_cause`, `reconciliation`, `production`, `downtime`, `hse_exposure`,
`hse_incidents`, `cash_call_event` (the last one reads back `bronze.reconciliation` and ports
Project Spark's `cashCallTrail()` submitted/under-review/settled|disputed logic exactly).

Real bugs hit and fixed during local + real-Fabric validation:
- `spark.createDataFrame(rows)` without an explicit schema fails when a column is all-null
  (`valid_to=None` for every dim row on first load) — fixed with explicit `StructType` schemas
  for all 10 tables.
- `ins_batchid`/`upd_batchid` are `IntegerType` (32-bit) in the real bronze schema — a
  `YYYYMMDDHHMM` batch id (12 digits) overflows that. Switched to `yymmddHH` (8 digits, hour
  granularity — plenty unique for a once-daily job).
- `DELTA_FAILED_TO_MERGE_FIELDS` on real Fabric (only visible via the pipeline-triggered run's
  richer error detail — the direct notebook-run REST API returns only
  `System_Cancelled_Session_Statements_Failed` with no cell detail) — caused by
  `bronze.dim_partner` already existing from an earlier failed attempt with a different
  (inferred) schema. Fixed by adding `.option("overwriteSchema", "true")` to the shared
  `_write()` helper, matching the convention already used in `nb_fetch_reports`.

Validated three ways before trusting it on real Fabric: (1) a pure-Python fake-spark harness for
row-generation logic, (2) a real local `SparkSession` with monkeypatched write/read (caught a
harness bug, not a generator bug — the monkeypatch on `DataFrame.write` didn't take effect while
`spark.table` did, so abandoned monkeypatching), (3) a real local `SparkSession` with a real
local Derby/Hive warehouse, full `createDataFrame(schema=...)` → `saveAsTable` → `spark.table`
read-back — passed clean. Then deployed and triggered on real Fabric via a wrapper pipeline
(`pl_daily_dummy_data`, single `TridentNotebook` activity) — **Completed, 2m48s**, all 10 bronze
tables written with real Delta writes confirmed via the pipeline's success status (direct
`GET .../lakehouses/{id}/tables` returns `400 UnsupportedOperationForSchemasEnabledLakehouse` —
that endpoint doesn't support schema-enabled lakehouses, so pipeline status + prior local
validation is the verification path instead).

**Extended `pl_daily_dummy_data` to the full chain** the user actually asked for ("trigger the
pipelines with dummy data on daily basis"): `generate_dummy_bronze` (`TridentNotebook`) →
`run_silver` (`ExecutePipeline` → `PL_SILVER_CONFIG`) → `run_gold` (`ExecutePipeline` →
`PL_GOLD_CONFIG`), each depending on the previous with `dependencyConditions: ["Succeeded"]`.
`PL_BRONZE_CONFIG` is deliberately skipped in the chain — it expects real extract files that don't
exist in this demo setup; the dummy generator already writes straight to `bronze.*`, replacing
that step's function. `PL_SILVER_CONFIG`'s generated notebook doesn't actually consume the
`domain`/`extract_id`/`processing_date`/`batchid` pipeline parameters it declares (confirmed via
grep), so placeholder values (`"customer0"`, `"dummy-daily"`, `@utcnow()`) are passed through safely.

Redeployed (87/87 items, incremental mode) and triggered via direct Fabric jobs API
(`POST .../jobs/instances?jobType=Pipeline`), polling `GET .../jobs/instances/{id}` for terminal
status. *(Result of this specific run — Completed/Failed and timing — logged in the next entry
once the poll returns.)*

Not yet done: removing the scratch `nb_diag.Notebook` / `bronze_diag` schema now that the
real generator is proven.

## Pivot: direct-to-gold, no daily refresh, chain approach abandoned (2026-09-06)

The bronze → silver → gold chain above kept failing with `TooManyRequestsForCapacity`
(HTTP 430) even after batching notebook concurrency down to 1-at-a-time in the shared
`build_layer_pipeline()` generator (`northstar-formation/src/northstar_formation/generators/pipelines.py`).
Diagnosed via the Fabric Livy sessions API
(`GET /v1/workspaces/{id}/spark/livySessions`) and the pipeline jobs API — the real cause
turned out to be a **stale pipeline run still `InProgress` in the background** (triggered
before a mid-session interrupt, never cancelled), silently holding the capacity's one
concurrent-Spark-session slot. Cancelled it directly
(`POST /v1/workspaces/{id}/items/{id}/jobs/instances/{jobId}/cancel`), confirmed
`GET .../spark/livySessions` showed 0 active sessions, and the exact same single-notebook
pipeline that had just failed then completed in 1m47s. Lesson: on a real capacity-constrained
(trial) workspace, always check for a stale `InProgress` job via the jobs/Livy-sessions API
before assuming a capacity error is structural — `az`/Fabric API job triggers keep running
server-side even if the polling session that triggered them is abandoned.

Decided (explicit user call, since this was burning real time for no lasting benefit): the
demo doesn't need a full daily bronze→silver→gold refresh at all, and the sequential/batched
concurrency change was never meant to be a standard behavior of the shared pipeline generator.
So:

1. **Reverted `northstar-formation/src/northstar_formation/generators/pipelines.py`** back to its original
   state — removed `_compute_levels`/`_chunk_by_concurrency`/`MAX_CONCURRENT_NOTEBOOKS`
   entirely, restored the auto-discovery activity loop's original hardcoded `"dependsOn": []`
   (full parallel). Regenerated `PL_SILVER_CONFIG`/`PL_GOLD_CONFIG`/`PL_BRONZE_CONFIG` and redeployed
   — confirmed back to fully-parallel activities, matching pre-session behavior. These three
   pipelines are no longer part of the demo-data flow at all (see below), so this only matters
   for whenever they're next used against real customer data on adequately-sized capacity.
2. **Added `nb_generate_dummy_gold.Notebook`** (`northstar-formation/models/customers/customer0/demo_data/`,
   mirrored into `northstar-deploy/configurations/customer0/versions/v1.0.0/demo_data/`) — writes
   FK-linked synthetic data **directly into `gold.*`**, one Spark session, no bronze/silver hop.
   Row-generation logic (partners/fields/periods, `_stable_rand`, reconciliation/production/
   cash-call formulas) is ported straight from `nb_generate_dummy_bronze.Notebook` (already
   proven against real Fabric and local Spark), adapted to gold's actual column set per
   `models/customers/customer0/gold/*.yaml`: natural keys only (no surrogate keys), no SCD/full
   audit columns (gold keeps just `Manifest_package`/`Manifest_file`), plus gold's computed
   columns (`VarianceBbl`, `VariancePct`, `Flag`, `ForecastVariancePct`) computed inline using
   the same threshold logic as the YAML `expression` fields. Validated with a local real-Spark
   dry run (`dry_run_gold.py`) before touching Fabric — clean pass, all 10 tables, 2,734 rows.
3. **`pl_daily_dummy_data.DataPipeline` rewritten to a single `TridentNotebook` activity**
   calling `nb_generate_dummy_gold` only (was: 3-activity bronze→silver→gold chain). Kept the
   same deployed `objectId`/`.platform` `logicalId` so this replaces the existing item rather
   than creating a new one. No daily schedule — this is a manually-triggered, one-shot (or
   occasional re-run) population, not a recurring job; **the "schedule daily midnight" task is
   dropped**, not just deferred.
4. Redeployed and triggered — **Completed in 1m47s**, all 10 gold tables populated
   (`gold.dim_partner`, `gold.dim_field`, `gold.dim_period`, `gold.dim_downtime_cause`,
   `gold.fact_reconciliation`, `gold.fact_production`, `gold.fact_downtime`,
   `gold.fact_hse_exposure`, `gold.fact_hse_incidents`, `gold.fact_cash_call_event`).

`nb_generate_dummy_bronze.Notebook` (and the Decimal-type fix applied to it — `EquityPct`,
`AllocatedBbl`/`LiftedBbl`/`CashCallUsd`, `ActualBopd`/`ForecastBopd`/`UptimePct`, `Hours`,
`HoursWorked` all changed from `DoubleType` to `DecimalType` matching each column's
`DECIMAL(p,s)` in `models/customers/customer0/bronze/*.yaml` — Delta rejects an in-place type
change via `ALTER TABLE REPLACE COLUMNS`) stays deployed but is no longer wired into any
pipeline; kept as a reference for whenever a real bronze-ingestion flow is needed later.

## Dynamic semantic model generation (2026-09-06)

Added `northstar-formation semantic-model` — a new CLI command that generates a Fabric SemanticModel
(TMDL, DirectLake) purely from `gold/*.yaml` models, so the semantic layer can never drift from
the star schema the gold notebooks actually produce. New generator module:
`northstar-formation/src/northstar_formation/generators/semantic_model.py`.

- **Tables/columns**: one `.tmdl` per gold table, columns read straight from each model's
  `transformations.columns`, SQL-style `data_type` mapped to TMDL (`NVARCHAR`→`string`,
  `INT`→`int64`, `DECIMAL`→`decimal` - every CUSTOMER0 decimal column has scale ≤ 3, fits Tabular's
  4-decimal-digit "Fixed Decimal Number" cleanly - `DATE`/`TIMESTAMP`→`dateTime`, `BOOLEAN`→
  `boolean`).
- **Relationships inferred automatically** - no manual wiring. Convention: a dim table's first
  declared column is its natural key (e.g. `PartnerId` for `dim_partner`); any fact table with a
  column of that same name gets a many-to-one relationship to that dim. Ran against CUSTOMER0's 10
  gold tables and correctly found all 13 real relationships (including that
  `fact_hse_incidents` has no `PartnerId` - correctly produced no partner relationship for it).
- **DirectLake, not Import** - partitions reference the lakehouse's SQL analytics endpoint via a
  shared `DatabaseQuery` M expression, no data duplication.
- Output path: `output_<customer>/semantic_model/<name>.SemanticModel`, a sibling of `ENG/` and
  `auth/` (same convention established earlier this session).

Command:
```bash
northstar-formation semantic-model \
  --models-dir models/customers/customer0 \
  --output output_customer0/semantic_model \
  --name sm_customer0 \
  --sql-endpoint <lakehouse SQL analytics endpoint FQDN> \
  --database-id <lakehouse SQL analytics endpoint database id>
```
Both values come from `GET /v1/workspaces/{id}/lakehouses/{id}` →
`properties.sqlEndpointProperties.{connectionString,id}`.

**Real bug caught and fixed via an actual deploy attempt** (not just a file-write): the first
publish failed with a real, precise Fabric error -
`Workload_FailedToParseFile` / `UnknownKeyword` on `expressions.tmdl` line 2. Root cause:
`expression DatabaseQuery = let` (with `let` glued onto the declaration line) makes the TMDL
parser treat `let` as the whole expression value, then choke on the next line as an
unrecognized property. Fixed by putting `let`/`in` on their own, deeper-indented lines - verified
against a real exported Fabric DirectLake `expressions.tmdl` (found via web search) before
retrying. Retried the exact same publish call with only that fix - **succeeded**. Full
customer deploy re-run afterward (97/97 items) to confirm nothing else regressed.

`northstar-deploy/configurations/customer0/config.yml` updated: `SemanticModel` added to
`item_types_in_scope` and to the end of `deployment_sequence` (deploys after
Notebook/DataPipeline, since it's DirectLake over the tables those populate). `Report` stays
excluded - no generated Report content exists yet.

### Deploy UI: semantic model / auth / report scope options

`northstar-deploy/deploy_ui.py` (the older multi-customer Streamlit deploy UI, separate from the
`deploy_orchestrator.py` path used for CUSTOMER0) had a "Deploy scope" selector limited to
All/Notebooks/Pipelines. Added three more: **Semantic models only**, **Auth only**, **Reports
only**. Supporting filters added to `northstar-deploy/deploy/deploy_cli.py`:
`_filter_semantic_models`, `_filter_reports` (by folder suffix), and
`_filter_items_by_path_segment` (for `auth/` - not identifiable by suffix alone, since it mixes
Notebook + DataPipeline; matched by checking `"auth"` is a path component relative to the repo
root). Also added `.SemanticModel`/`.Report` to `_FABRIC_SUFFIXES` so `_discover_items_in_repo`
picks them up at all - they were missing entirely before.

**Reports always deploy after semantic models**: when "Reports only" is selected, the UI now
injects a preceding plan step scoped to just that target's `.SemanticModel` items before the
Report step, so a Report's binding to its SemanticModel always resolves. Implemented as two
separate sequential plan entries for the same target (not a single combined deploy call) - the
plan's existing stable sort by kind/environment preserves their insertion order, so no changes
were needed to the actual deploy-runner loop.

## Project Spark hosted on Azure App Service - Phase 1 (2026-09-06)

Goal: get the Lovable-generated frontend (`Project Spark/`, a TanStack Start app) hosted for
real on Azure App Service, no Docker. Deliberately scoped to hosting only - the app still
serves its own built-in mock data (`src/data/delta-basin.ts`); wiring it to the real Fabric SQL
endpoint is a separate follow-up (Phase 2).

**Real, non-obvious blocker found before touching Azure at all**: `Project Spark/vite.config.ts`
uses `@lovable.dev/vite-tanstack-config`, whose Nitro build target **defaults to
`cloudflare-module`** (Lovable's own hosting target) when not overridden. Left as-is, `npm run
build` produces a Cloudflare Worker bundle, not a runnable Node server - would have silently
failed on App Service. Fixed by passing `nitro: { preset: "node-server" }` into the top-level
`defineConfig()` call (confirmed via the package's own `.d.ts` - `nitro?: true | { preset?:
string }`). Verified locally: `npm run build` → `.output/server/index.mjs`; ran it directly with
`PORT=... node .output/server/index.mjs` and curled it - real 30KB SSR HTML, correct title. Also
added a `"start"` script for clarity, though App Service uses an explicit `app_command_line`
instead of relying on Oryx's default Node startup detection (which looks for `server.js`/
package.json `main` at the repo root - would never have found `.output/server/index.mjs`).

Local build required Node ≥22.12 (`engine-strict=true` in `.npmrc`, and the repo's system Node
was v20) - used Homebrew's `node@22` directly (`/opt/homebrew/opt/node@22/bin/node`) rather than
changing the system default.

**Terraform** (`terraform/app_service.tf`, new file) - added to the same stack as everything
else this session, one `apply` workflow:
- `azurerm_service_plan.spark` - Linux, B1 SKU (cheapest tier with Always On, fine for a pilot).
- `azurerm_linux_web_app.spark` - Node 22 LTS runtime (`node_version = "22-lts"`),
  `app_command_line = "node .output/server/index.mjs"`, `use_32_bit_worker = false` (explicit -
  the provider's default for a new Linux web app is `true`, wrong for a real Node process),
  `always_on = true`, `SCM_DO_BUILD_DURING_DEPLOYMENT = "true"` so Azure runs Oryx
  (`npm install && npm run build`) server-side on deploy instead of us shipping
  `node_modules`/`.output` ourselves.
- New outputs: `spark_app_url`, `spark_app_name`.

Applied cleanly (2 added, 1m2s). Real URL:
**`https://app-northstar-customer0-dev-spark.azurewebsites.net`**

**Deploy** (fully CLI, no portal):
```bash
cd "Project Spark"
git ls-files -z --cached --others --exclude-standard | xargs -0 zip -q /tmp/spark-deploy.zip
az webapp deploy \
  --resource-group rg-northstar-customer0-dev \
  --name app-northstar-customer0-dev-spark \
  --src-path /tmp/spark-deploy.zip \
  --type zip
```
Zipping via `git ls-files` (tracked + untracked-but-not-ignored) naturally excludes
`node_modules`/`.output`/etc. since they're already in the project's own `.gitignore` - no
manual exclude list needed.

**Real gotcha hit**: `az webapp deploy` returned `504 GatewayTimeout` from the CLI itself - looked
like a hard failure, but the Oryx build was still genuinely running server-side (Kudu doesn't
care that the client gave up). Confirmed via
`az webapp log deployment list -g rg-northstar-customer0-dev -n app-northstar-customer0-dev-spark` showing
`"progress": "Running oryx build..."`, `"complete": false` - polled that same command every 20s
until `complete: true`. **Lesson for next time**: `az webapp deploy`'s synchronous wait has a
shorter timeout than a cold Oryx build of a dependency-heavy app can take - don't treat a 504
from the CLI as deploy failure by itself; check `az webapp log deployment list` before retrying
or investigating further.

Verified live: `curl https://app-northstar-customer0-dev-spark.azurewebsites.net/` → `HTTP 200`, real
30KB server-rendered HTML, same content as the local `.output/server/index.mjs` smoke test.

## Project Spark wired to real Fabric data - Phase 2 (2026-09-07)

Goal: replace `delta-basin.ts`'s static mock arrays with real per-request `gold.*` data over the
lakehouse's SQL analytics endpoint, keeping every derived calculation (variance flags, TRIR,
cash-call trails, alerts, etc.) working identically. Chose the full live-per-request approach
(not a build-time snapshot) - real user decision, since a snapshot wouldn't reflect subsequent
re-runs of the dummy-data generator.

**Real scope discovery before writing code**: `delta-basin.ts` is 665 lines of module-level
static arrays with ~25 functions closing over them, imported directly (not via props/context) by
7 routes and 4 shared components (`app-shell`, `field-schematic`, `period-context`, `ui-kit`).
Getting genuinely live data meant touching all of it - refactored the whole file into a
`createDeltaBasin(raw: RawDeltaBasin)` factory (same logic, parameterized instead of closing over
module consts), kept a `generateMockRaw()` + `mockDeltaBasin` fallback for local dev / connection
failure, and threaded live data through a new `DeltaBasinProvider` context (mirroring the app's
existing `CatalogProvider` pattern) fed by a TanStack Start root-route `loader` that primes a
React Query cache entry (`queryClient.ensureQueryData`) before the tree renders - no loading
flash, works identically for SSR and client navigation. `partners.$partnerId.tsx`'s own route
`loader` (needs `partners` outside React, to validate the URL param) calls the same
`ensureQueryData` call with the same query key - React Query dedupes it, no double-fetch.

Three of the original PRNG "derived" functions (`downtimeForPeriod`, `cashCallTrail` and friends)
were actually synthesizing data that now has a real source table
(`gold.fact_downtime`/`gold.fact_cash_call_event`, both built earlier this session) - replaced the
PRNG synthesis with real lookups/grouping against fetched rows, so the cash-call trail shown in
the UI is now traceably the same data the backend actually generated, not a second independent
synthesis.

**Server-only data layer** (`Project Spark/src/data/fabric-data.ts` - NOT `src/server/`, see real
bug below): `mssql` + `@azure/identity`'s `DefaultAzureCredential`, requests an AAD token for
`https://database.windows.net/.default`, connects via `authentication: { type:
"azure-active-directory-access-token" }`. Queries all 10 `gold.*` tables, reshapes to
`RawDeltaBasin`. Wrapped in a `createServerFn` (TanStack Start) so `mssql`/`@azure/identity` never
reach the client bundle - verified directly (`grep -l mssql .output/public/**/*.js` → no matches).
Falls back to `null` (caller falls back to mock) on any failure rather than crashing the page -
proved genuinely necessary, not theoretical (see below). Added a 5-minute in-process cache
(`gold.*` changes at most daily) so normal traffic doesn't open a fresh SQL connection per
request.

**Real bug caught by the build itself, not guessed**: first build failed with
`[import-protection] Import denied in client environment - Denied by file pattern: **/server/**`
- this project's TanStack Start plugin config blocks ANY import matching `**/server/**` from
client-reachable code, regardless of `createServerFn` wrapping (a stricter guard on top of the
framework's own client/server split, presumably to stop secrets leaking by path convention alone).
Fixed by moving the file from `src/server/fabric-data.ts` to `src/data/fabric-data.ts` - same
`createServerFn` mechanism, just outside the blocked path.

**Real transient failure caught during local testing, not theoretical**: testing against the
real SQL endpoint locally (SPN via `DefaultAzureCredential`'s env-var credential, same values
used throughout this session), 4/5 rapid requests succeeded with real data (`[fabric-data]
fetched: partners 5 fields 5 periods 24 reconciliation 600`) but one hit a genuine
`ConnectionError: Failed to connect ... in 15000ms` - and the page still rendered successfully
(fell back to mock data, no crash), proving the fallback path is load-bearing, not decorative.
The in-process cache added afterward reduces how often this can happen in practice (one fetch per
5 minutes instead of one per request).

**Terraform** (`terraform/app_service.tf`): added `identity { type = "SystemAssigned" }` to
`azurerm_linux_web_app.spark`, and a `fabric_workspace_role_assignment` granting that identity's
own `principal_id` the `Viewer` role on the Fabric workspace - same
`fabric_workspace_role_assignment` mechanism already used for admin_users/admin_spns
(`fabric_workspace.tf`), since a managed identity is just another AAD service principal. No
secrets anywhere - the app authenticates to Fabric as itself. `FABRIC_SQL_ENDPOINT`/
`FABRIC_DATABASE_ID` app settings sourced directly from
`fabric_lakehouse.lkh_001.properties.sql_endpoint_properties.{connection_string,id}` - fully
dynamic via Terraform, no manual API lookup needed (unlike Phase 1, where I fetched these by hand
via a direct API call).

**Real Terraform sequencing issue**: `fabric_workspace_role_assignment.spark_app_viewer`'s
`principal.id = azurerm_linux_web_app.spark.identity[0].principal_id` failed at plan time -
`Missing Configuration for Required Attribute` - the `fabric` provider's `principal.id` doesn't
accept an unknown/computed value at plan time the way most provider attributes do. Fixed with a
two-step apply: `terraform apply -target=azurerm_linux_web_app.spark` first (materializes the
identity's real `principal_id`), then a normal `terraform plan`/`apply` picks up the role
assignment with a concrete value already in state.

Deployed via the same `git ls-files | zip | az webapp deploy` flow as Phase 1 - same 504-from-CLI-
but-still-building gotcha recurred (Oryx build is heavier now with `mssql`/`@azure/identity`
pulled in), same fix: poll `az webapp log deployment list` instead of trusting the CLI's
synchronous wait.

**Final verification** (not just HTTP 200 - that alone doesn't distinguish real data from a
silent mock fallback, by design): enabled filesystem application logging
(`az webapp log config --application-logging filesystem`), restarted the app to clear its
in-process cache, tailed live logs while hitting the real URL -
**`[fabric-data] fetched: partners 5 fields 5 periods 24 reconciliation 600`** appeared in the
live container's stdout, proving the deployed app authenticated via its own managed identity
(zero secrets configured anywhere) and pulled real `gold.*` data end-to-end.

## Standardized output tree: auth / data_modelling / data_engineering (2026-09-07)

Real user requirement: every customer's generated output must follow a fixed folder convention,
visible under `output_<customer>/` even before deployment:
```
output_<customer>/
  auth/
  data_modelling/
    semantic_models/
    reports/                (empty until a Report generator exists)
  data_engineering/
    notebooks/
    pipelines/
    lakehouses/
      <lakehouse_name>.Lakehouse/   (reference-only placeholder, see below)
    demo_data/
```

Turned out to need almost no code changes - `-o`/`--output` are all caller-supplied paths
already, and `copy_auth_files()`'s `output_dir.parent / "auth"` logic is generic (works the same
whether `output_dir` is named `ENG` or `data_engineering` - only the *name* changed, not the
relationship). Just re-ran the existing commands with new `-o` values:
```bash
northstar-formation transform ... -o output_customer0/data_engineering/sql
northstar-formation transform ... -o output_customer0/data_engineering/ --generate-notebooks lkh_001 ...
northstar-formation pipelines ... -o output_customer0/data_engineering/pipelines
northstar-formation semantic-model ... --output output_customer0/data_modelling/semantic_models
```

Two genuinely new pieces of tooling added (`northstar-formation/src/northstar_formation/generators/library_copy.py`):
- **`copy_demo_data_files()`** - demo_data was previously copied by hand (`cp -r`) earlier this
  session; now automated the same way `copy_auth_files()` already was, wired into the `transform`
  CLI command right after the auth copy. Unlike `auth/` (shared across all customers, copied to
  `output_dir.parent`), `demo_data/` is customer-specific (lives under
  `models/customers/<customer>/demo_data/`) and copied *nested* under the engineering output
  (`output_dir / "demo_data"`), not as a sibling.
- **`write_lakehouse_placeholder()`** - writes a minimal `.Lakehouse` folder (just `.platform`,
  no `definition/` - Lakehouses have no git-syncable definition content) for visibility in the
  tree. **Deliberately not added to any customer's `item_types_in_scope`** - Lakehouses stay
  Terraform-managed (`terraform/fabric_lakehouse.tf`); including "Lakehouse" in fabric-cicd's
  scope risks it treating the Terraform-created Lakehouse as an orphan to delete during cleanup
  (the exact risk already documented in `config.yml`'s comments from earlier this session). This
  folder is reference-only and changes no deployment behavior.
- `semantic-model` command now also ensures an empty `reports/` sibling directory under
  `data_modelling/` (with a `.gitkeep`), so the full tree shape is always present even though no
  Report generator exists yet.

**Redeployed `northstar-deploy/configurations/customer0/versions/v1.0.0/`** to match - physically moved
(not regenerated) `notebooks/`→`data_engineering/notebooks/`,
`pipelines/`→`data_engineering/pipelines/`, `demo_data/`→`data_engineering/demo_data/`,
`semantic_model/sm_customer0.SemanticModel`→`data_modelling/semantic_models/sm_customer0.SemanticModel`;
added `data_engineering/lakehouses/lkh_001.Lakehouse/` and `data_modelling/reports/`; `auth/`
stayed where it already was (already matched the spec). Confirmed safe before redeploying: fabric-
cicd matches items by each `.platform` file's `logicalId`, not by physical folder path, and none
of `northstar-deploy`'s own scripts (`deploy_orchestrator.py`/`config_models.py`) hardcode any subpath
under `repository_directory` - grepped to confirm. Redeploy succeeded, 96/96 items (one fewer than
before: also removed the leftover scratch `nb_diag.Notebook` from `demo_data/` while restructuring
- confirmed via a direct Fabric API check afterward that it's genuinely gone from the live
workspace, not just missing from the repo).

## Full unpublish + clean redeploy (2026-09-07)

Real user request: wipe everything currently in the `customer0-dev` workspace and deploy fresh, to
guarantee zero drift after all the folder restructuring above.

`fabric-cicd` doesn't expose an "unpublish everything" helper (`unpublish_all_orphan_items` only
removes items *not* present in the repo - not useful here, since the repo already matched the
workspace). Did it directly via the Fabric REST API instead: listed every item in the workspace
(98 total: 90 Notebook, 5 DataPipeline, 1 SemanticModel, 1 SQLEndpoint, 1 Lakehouse), filtered to
just `Notebook`/`DataPipeline`/`SemanticModel` (96 items) and `DELETE`d each one individually -
**deliberately leaving `Lakehouse` and its companion `SQLEndpoint` untouched**, since the
Lakehouse is Terraform-managed and holds the real bronze/silver/gold data; deleting it would
destroy actual demo data, not just redeployable code.

Real transient failure mid-run: the first pass deleted 63/96 cleanly, then started failing with a
generic `UnknownError` (400) on every remaining `DELETE` call - all DataPipelines and the
SemanticModel had already gone through fine, only Notebooks were affected, and it wasn't a
dependency-ordering issue (nothing referenced them anymore). Looked like transient Fabric API
instability rather than a real permission or state problem. Retried the remaining 33 with a
per-call delay and a 3-attempt retry loop - all 33 succeeded. Confirmed via a direct API list call
that only `Lakehouse` + `SQLEndpoint` remained before redeploying.

Ran `deploy.py --mode full` against the now-empty workspace - **98/98 items republished**,
exactly matching the pre-wipe count (90 Notebook, 5 DataPipeline, 1 SemanticModel, plus the
untouched Lakehouse/SQLEndpoint), confirming zero drift between the repo and what's actually
live.

## Semantic model measures + self-service Report attempt (2026-09-07)

Added a small set of real DAX measures to `sm_customer0` (`Total Allocated Bbl`, `Total Lifted Bbl`,
`Avg Variance Pct`, `Total Cash Call USD` on `fact_reconciliation`; similar on
`fact_production`/`fact_downtime`/`fact_hse_exposure`/`fact_hse_incidents`) - both because a
self-service report needs pre-aggregated values users can drag onto a visual without knowing
DAX, and to avoid an unconfirmed `Aggregation` field-wrapper syntax in hand-authored PBIR visual
JSON. Verified real TMDL `measure` syntax via the official Microsoft docs before writing (same
discipline as the earlier `expressions.tmdl` fix) - deployed cleanly, no issues.

**New `northstar-formation report` command** (`generators/report.py`) generates a minimal self-service
Fabric Report (PBIR format) bound live to a SemanticModel via `byConnection` - 4 KPI cards, a
period/partner slicer pair, a trend chart and a reconciliation detail table on one page, meant as
a starting point users duplicate/extend, not a finished dashboard. Real PBIR syntax (visual.json
query/projections, page.json, pages.json, report.json, definition.pbir) researched and verified
against a real, working example repository
(`github.com/data-goblin/power-bi-agentic-development`) before writing any generator code - same
discipline as every other hand-authored Fabric format this session.

**Not currently deployed** - `sr_customer0.Report` fails to publish with a generic
`Content provider provided invalid package content stream` error from Fabric's Report import
API, not resolved despite:
- Fixing a real, confirmed schema error first (`report.json` requires `themeCollection` -
  added, using a real theme reference `CY25SU12`, tried both `CY24SU10` and `CY25SU12`, no
  difference).
- Reading `fabric-cicd`'s own `_items/_report.py` source directly and discovering it only
  auto-converts a `byPath` `definition.pbir` reference into a specific legacy `byConnection`
  shape (`pbiModelVirtualServerName: sobe_wowvirtualserver`, `pbiModelDatabaseName`,
  `connectionType: pbiServiceXmlaStyleLive`) - switched from the newer documented
  `connectionString: semanticmodelid=...` form to hand-author this exact shape instead, since
  it's the only path this library's own code actually exercises. No change in outcome.
- Binary-searching by testing with all 8 visuals stripped out entirely (still fails identically)
  and with the empty `visuals/` folder removed entirely (still fails identically) - proving the
  problem is in the report "shell" (report.json/page.json/pages.json/version.json/
  definition.pbir/.platform), not the hand-authored visual JSON.
- Reading `fabric_workspace.py`'s generic `_publish_item`/`File.base64_payload` - confirmed
  the packaging mechanism (per-file base64 parts) is the same proven-working path already used
  successfully for every other item type this session.

Root cause still unknown after this much diagnostic work. `item_types_in_scope` for customer0 does
**not** include `Report` right now - removed after this investigation so it doesn't block the
rest of deployment. The generator code and this diagnostic trail stay in place; re-attempt by
picking up from "shell file structure is the problem, not the visuals" rather than starting over.

## Rebrand + access logging into the lakehouse (2026-09-07)

Renamed `Project Spark/` → `frontend/` (`git mv`, preserves history - 101 files renamed cleanly).
No other part of the stack references the old path by name (Terraform only knows the deployed
App Service name, which is independent of the source folder name), so this was a pure rename
with no follow-on config changes needed. Removed the Lovable-branded `favicon.ico` and
`twitter:site: @Lovable` meta tag; replaced the favicon with a small hand-authored SVG (a Δ mark
in the app's own existing brand teal) rather than a fabricated logo - no real CUSTOMER0 or Delta Basin
logo asset exists to use instead.

**Webapp access logging, visible in the lakehouse** - real architecture constraint worth
recording: the Fabric SQL analytics endpoint is **read-only** (confirmed earlier this session
when building the data-fetch side) - it cannot accept `INSERT`s, so there's no way for the app to
write access events through the same connection it reads `gold.*` through. Built a separate write
path instead, matching this project's existing bronze-ingestion philosophy (raw files landed
first, a notebook turns them into a real Delta table) rather than trying to write Delta/Parquet
format directly from Node (not attempted - reimplementing Delta's transaction log format outside
Spark is real complexity for no benefit here):

1. **`frontend/src/data/access-log.ts`** (server-only) - a `createServerFn` that captures
   `getRequestIP({ xForwardedFor: true })` and the `user-agent` header server-side
   (`@tanstack/start-server-core` - confirmed via its `.d.ts`, not guessed), then writes one
   small NDJSON file per page-visit event straight to the Lakehouse's `Files/access_logs/<date>/`
   via the OneLake DFS (ADLS Gen2-compatible) REST API - `PUT ?resource=file` →
   `PATCH ?action=append` → `PATCH ?action=flush`, authenticated as the app's own managed
   identity via `DefaultAzureCredential` against the `https://storage.azure.com/.default` scope
   (different scope than the SQL endpoint's `https://database.windows.net/.default`).
2. **`frontend/src/components/access-log-tracker.tsx`** - a client-side component (wired into
   `AuthGate` in `__root.tsx`, only active once signed in) that tracks page-entry time and, on
   each route change, logs the page just left with its real dwell time (`Date.now()` delta).
   Known, documented gap: the very last page before a tab close isn't captured - would need a
   `sendBeacon`-compatible endpoint, not attempted here.
3. **`northstar-formation/models/customers/customer0/demo_data/nb_ingest_access_logs.Notebook`** (new,
   hand-written like the other demo_data notebooks, not YAML-model-derived) - reads all NDJSON
   under `Files/access_logs/*/*.json` via `spark.read.json` (handles the missing-folder case,
   which is the normal state before any traffic exists), appends into
   `bronze.webapp_access_log`, then deletes each successfully-ingested source file
   (`notebookutils.fs.rm`) so re-runs don't duplicate events. Not on any fixed schedule -
   deliberately left as run-manually-or-set-your-own-Fabric-schedule, matching the "no daily
   refresh assumed" pattern already established for the other demo notebooks.
4. **Terraform**: the app's managed identity role upgraded from `Viewer` → `Contributor` on the
   Fabric workspace (`terraform/app_service.tf`) - Viewer only grants OneLake read access,
   Contributor is the smallest role that also allows writes. Added `FABRIC_WORKSPACE_ID`/
   `FABRIC_LAKEHOUSE_ID` app settings (not secrets, just addressing - auth is still purely via
   managed identity). Also declared the `logs.application_logs` block Terraform-side (was
   previously only set via an ad-hoc `az webapp log config` CLI call earlier this session, which
   would have silently drifted back out on the next unrelated `apply` otherwise).

**Known, deliberate gap**: "location" is recorded as the raw client IP only - no geo-IP
resolution (city/country). Real geo lookup means either an external geo-IP API in the request
path (added latency, a new dependency, and a genuine data-residency/privacy decision that
shouldn't be made unilaterally) or batch-resolving IPs later in the ingestion notebook. Flagged
rather than silently either adding an unvetted external dependency or claiming "location" is
fully implemented when it isn't.

## Access-log corrections + real login allowlist (2026-09-07)

Four follow-up corrections to the access log, plus a new, real authorization gate for the login
page - both landed in the same pass since the login work reused infrastructure this session
already had in place for the log.

**Access log corrections:**
1. Table moved from `bronze.webapp_access_log` to **`log.webapp_access_log`** -
   `nb_ingest_access_logs` now does `CREATE SCHEMA IF NOT EXISTS log`. This wasn't inventing a new
   convention: this lakehouse already has a `log` schema in active use for the other audit tables
   (`log.audit_operation_log`, `log.audit_package_lifecycle`, `log.dim_date`, `log.dim_time`).
2. **Login and logout now flow through the same pipeline as page visits.** Added an `eventType:
   "login" | "logout" | "page_visit"` field to `AccessLogEvent`. `login.tsx`'s `completeLogin()`
   and `app-shell.tsx`'s `ProfileMenu` logout handler both call `logAccessEvent` directly now -
   previously only page-navigation dwell events reached the lakehouse; login/logout only existed
   in the separate, browser-only `activity-log-context.tsx` (which still fires too, unchanged -
   it serves the in-app RBAC log-visibility feature, a distinct concern).
3. **"Very quick to write to the table."** Real architecture tension: the OneLake file write
   itself was already fast (~1-2s, confirmed with a real write test earlier this session) - the
   actual latency was between a file landing and `nb_ingest_access_logs` turning it into a
   queryable row, since that notebook had no schedule at all. Two options considered: (a) a
   hand-rolled direct Delta writer from Node, or (b) Fabric's Eventstream real-time-ingestion
   feature. Rejected both for this pass - (a) risks corrupting a lakehouse that holds all of this
   session's real demo data if the hand-written Parquet/Delta transaction log has any bug, and
   (b) is a new, unfamiliar Fabric item type with its own unknown-territory risk, same class of
   problem the Report item type turned into earlier this session. Went with the safe, boring fix
   instead: scheduled `nb_ingest_access_logs` via the Fabric Job Scheduler API
   (`POST /v1/workspaces/{ws}/items/{item}/jobs/RunNotebook/schedules`, `type: "Cron", interval:
   5` - minutes) so events land in the table within a few minutes instead of never.
4. **Country/city/continent added**, resolved in the ingestion notebook via `ip-api.com`'s free,
   keyless batch endpoint (up to 100 IPs/call), joined back onto the batch by IP after ingestion -
   deliberately *not* resolved on the write path, since a synchronous external API call there
   would directly fight point 3. A failed/rate-limited lookup just leaves those columns null for
   that pass rather than failing the whole ingestion.

**Login allowlist** (separate but related ask - restrict login to two real emails instead of
"any email signs you in"): found this session already has the infrastructure for exactly this
from earlier work under `northstar-formation/auth/` (`nb_get_users`, `nb_fetch_reports`, `nb_auth`,
`nb_access_control`, `pl_auth.DataPipeline`) - `nb_get_users` already read `Files/users.csv` into
`dbo.users`, just needed pointing at the actual format requested (`user|user_group`, pipe-
delimited - added `.option("sep", "|")`). Uploaded `Files/users.csv` with the two authorized
emails (`mucapera@gmail.com`, `brumeto@gmail.com`, both `user_group=ALL`), triggered
`nb_get_users` once immediately (on-demand `RunNotebook` job) so the table wasn't empty until the
next scheduled run, and scheduled `pl_auth` itself daily at midnight UTC (`type: "Daily", times:
["00:00"]`, `jobType: "Pipeline"` this time, not `RunNotebook`) so a future edit to `users.csv`
takes effect the next night without a manual trigger.

New `frontend/src/data/auth-check.ts` (server-only) queries `dbo.users` over the SQL endpoint and
**fails closed** - if the query itself fails for any reason, nobody gets in, rather than silently
falling back to open access. `login.tsx` now awaits this check before calling `login()`; a
rejected email shows an inline error instead of signing in. `resolveDemoUser`'s old
any-email-defaults-to-executive behavior is gone; `resolveAuthorizedUser` maps `user_group` to a
`PersonaId` only when they already match one of the four existing personas, and otherwise falls
back to `executive` (the broadest view) - real per-group permissions are explicitly deferred
("later we will define what each user group has access to"), so this is a coarse placeholder, not
a finished permission model. The demo-persona emails (`exec@customer0.com` etc.) and the old
`DEMO_LOGIN_HINTS` copy are gone from the login page since they're no longer valid logins; "Continue
with CUSTOMER0 EntraID" now simulates signing in as `mucapera@gmail.com` specifically rather than a
fixed demo persona, since that's an actually-authorized identity.

**Real bug found and fixed while verifying this**: the first deploy of the login gate returned a
silent `403 Forbidden` on every real browser login attempt, never reaching the SQL check at all.
Root cause: TanStack Start's built-in CSRF middleware compares the browser's `Origin` header
against `new URL(request.url).origin` - and Azure App Service terminates TLS at its front-end and
forwards plain HTTP to the Node process, so `request.url` inside the app was `http://...` while
every real browser sends `Origin: https://...`. Guaranteed mismatch, for every client-invoked
server function, not just this one - meaning this same bug would have silently broken the
access-log writes too, had they been checked this closely. Fixed in `frontend/src/server.ts`
(the existing custom SSR entry point) by rewriting the incoming request's protocol from
`X-Forwarded-Proto` before handing it to the TanStack handler - same "explicitly read the
forwarded header, don't assume the framework trusts it automatically" pattern already used for
`getRequestIP({ xForwardedFor: true })` elsewhere in this codebase. Confirmed fixed with a real
Playwright browser run against the live site (not curl - curl can't easily replicate the
client's exact RPC wire format, and an early curl-based check gave a false negative against a
mid-restart container besides): `mucapera@gmail.com` reaches `/`, `exec@customer0.com` is rejected
with the inline error, zero console errors either way.

Along the way, needed the Fabric SPN's client secret (Key Vault `kv-northstar-customer0-dev` /
`customer0-spn-client-secret`) for the first time this session from a cold shell - confirmed directly
that the human `az login` identity cannot substitute (401 listing workspace items; Fabric APIs
also reject personal Microsoft accounts outright regardless, per the note earlier in this log).
Wrote the SPN credential to `northstar-deploy/.env` (gitignored, `chmod 600`) rather than re-fetching it
from Key Vault on every command - matches `deploy.py`'s own built-in `.env`-loading behavior, so
this doubles as the project's normal local-dev credential file going forward.

**Known risk, not fixed this pass**: `pl_auth`'s own DAG (`fetch_reports` and `get_users` both
have `dependsOn: []`, i.e. run in parallel) needs two concurrent Spark sessions just for itself.
Tested the newly-scheduled pipeline twice on-demand and both runs failed with
`TooManyRequestsForCapacity` (HTTP 430) on `get_users` - this workspace's capacity is `F2`
(`terraform.tfvars`), the smallest SKU, and apparently can't sustain 2 concurrent Livy sessions
reliably, more so now that `nb_ingest_access_logs` also holds a session every 5 minutes. This
predates today's change (`pl_auth`'s DAG shape came from the earlier `auth/` import, not touched
today) - today's change only added the midnight schedule on top of an already-fragile pipeline.
The part that actually matters for login, `nb_get_users` alone, has run standalone successfully
twice (`dbo.users` is confirmed populated and correct) - so the login gate itself works today,
but the midnight `pl_auth` schedule may fail some or most nights on this capacity tier until
either the SKU is upsized or `pl_auth`'s DAG stops running both notebooks in parallel. Left
alone rather than redesigning `nb_auth`/`pl_auth` unprompted - their actual logic (dataset
mappings, permission matrix) is explicitly deferred per "later we will define what each user
group has access to."

---

## Real star-schema fix: dim_/fact_ naming, integer surrogate keys (2026-09-07)

Four related corrections, all one underlying fix: "dims and facts should only exist in gold, not
bronze/silver; these tables should be renamed; fact IDs should be integers, hashed from each
dim's natural key; facts shouldn't carry dim text values, only keys referencing dims."

**Found the exact precedent already in this repo** before writing anything: `models/_base/`
(shared across every real customer) already does
exactly this - bronze/silver never prefix table names (`machine.yaml`, `pplmachinefact.yaml`),
only gold does (`dim_machine.yaml`, `fact_pplmachinefact.yaml`), and gold dims/facts already use
`CAST(xxhash64(<natural_key>) AS BIGINT)` surrogate keys (e.g. `dim_customer_operations.yaml`'s
`Customerid_key`, `fact_pplmachinefact.yaml`'s `Machineid_key`/`Unitid_key`/etc, with the dim
keeping both the hash key and the natural-key/text attribute, the fact keeping only the hash
key). **CUSTOMER0 was the one customer that deviated** - its bronze/silver had `dim_partner.yaml`
etc, and its gold facts carried plain NVARCHAR `PartnerId`/`FieldId`/`PeriodId` instead of hashed
BIGINT keys. This was a correction to match the framework's own established convention, not a
new convention invented for this pass - kept the fix scoped to CUSTOMER0 only, since the other
customers already follow it correctly and touching their live models wasn't
requested or warranted.

**Changes:**
1. `models/customers/customer0/{bronze,silver}/dim_{partner,field,period,downtime_cause}.yaml`
   renamed to drop the `dim_` prefix (`partner.yaml` etc, `model.name` and all
   `base_table`/`extends`/`depends_on_tables` cross-references updated to match). Gold keeps the
   `dim_`/`fact_` prefix - that's star-schema layer naming, which is correct there.
2. Gold `dim_*.yaml`: added a new first column `<X>Id_key = CAST(xxhash64(<X>Id) AS BIGINT)`
   (BIGINT), `merge_keys` switched to the new key column, the plain natural-key/text columns
   kept unchanged as attributes.
3. Gold `fact_*.yaml`: every column that referenced a dimension (`PeriodId`, `FieldId`,
   `PartnerId`, `CauseId`) replaced with its `_key` hash equivalent; `merge_keys` updated to
   match. Columns that aren't dimension references - `fact_hse_incidents.IncidentId` (the fact's
   own natural key, not an FK) and `fact_cash_call_event.Stage` (a status attribute, no `dim_stage`
   exists) - deliberately left untouched; the ask was specifically about keys that reference
   dims.
4. **`semantic_model.py` needed zero code changes** - `infer_relationships()` was already
   generic (matches a fact column name against a dim's first declared column), so once the YAML
   declared `PartnerId_key` as `dim_partner`'s first column and the matching fact column had the
   identical name, relationship inference picked up all 13 fact→dim relationships correctly on
   regeneration, now on real integer keys (a genuine DirectLake performance win too, not just a
   modeling correctness one).
5. **The real work was in `nb_generate_dummy_gold.Notebook`** - the actual live data path.
   Discovered along the way: `pl_daily_dummy_data.DataPipeline`'s only activity is
   `generate_dummy_gold` - the bronze→silver→gold YAML-driven transform notebooks
   (`brz_partner.Notebook` etc, regenerated from the YAML above) are **not** on the automated
   path at all; this one hand-written notebook writes gold directly. Updated its `_write()`
   helper to take `hash_keys`/`drop_hashed` params - computes `xxhash64(col).cast("bigint")` via
   real PySpark (not a Python-side hash, so values would match the YAML-driven path exactly if
   that path is ever actually run), adds the `_key` column, and for facts drops the original
   natural-key column afterward. Also renamed the same 4 dim tables in
   `nb_generate_dummy_bronze.Notebook` for consistency, even though that notebook isn't
   scheduled either.
6. **`frontend/src/data/fabric-data.ts`** - since gold facts no longer carry the plain string
   PartnerId/FieldId/PeriodId/CauseId, but the rest of the frontend (types, routes, display)
   still needs those strings, rewrote the SQL queries to JOIN each fact to its dim(s) on the new
   `_key` columns and SELECT the dim's natural key back under the same name. Zero changes needed
   anywhere else in the frontend - same query shape in, same shape out.

**Deploy gotchas hit and fixed, not routed around:**
- `northstar-formation transform`'s notebook/SQL generation is purely additive into `output_customer0/` -
  it doesn't delete files an earlier run created under old names. After the rename, stale
  `brz_dim_partner.Notebook` (etc) sat alongside the new `brz_partner.Notebook`, and the
  DDL-notebook generator picked up BOTH (`bronze=14` instead of the correct `bronze=10`),
  producing a DDL notebook with duplicate/stale `CREATE TABLE bronze.dim_partner` statements
  alongside the correct ones. Fixed by deleting the stale `*.sql`/`*.Notebook` output by hand
  before regenerating, then confirming the DDL notebook's table count matched exactly
  (bronze=10, silver=10, gold=10).
- `northstar-formation pipelines` unconditionally copies `00_PRE_ORCH`/`01_ORCH`/`DEMO_GENERATOR` -
  generic multi-domain (FCT/OPR) master-orchestration pipelines from the shared `_c000` library -
  into whatever `-o` you give it. These were never part of CUSTOMER0's deployment before (confirmed
  via `git status` - completely untracked), reference notebooks CUSTOMER0's minimal pilot doesn't
  have, and made the DataPipeline deploy step fail outright (`PublishError: Failed to publish 5
  item(s)`). Removed them from the sync target rather than debugging references that were never
  meant to exist for this customer - not a bug in the rename, a side effect of running a command
  with unconditional behavior against a customer it wasn't scoped for.
- After redeploying and rerunning the DDL + gold-generator notebooks, direct SQL queries against
  `gold.dim_partner`/`gold.fact_reconciliation` still showed the *old* shape (no `_key` column,
  plain-text `PartnerId` still on the fact) - looked like the notebooks hadn't actually run the
  new code. Verified two ways before assuming that: (1) fetched the *live* notebook definition
  via `getDefinition` and confirmed it had `xxhash64`/`PartnerId_key` in it - the correct code
  was deployed; (2) read the Delta table's own `_delta_log` commit JSON directly over OneLake
  (bypassing SQL entirely) and confirmed the physical schema was already correct
  (`fact_reconciliation`: `PeriodId_key, FieldId_key, PartnerId_key` and nothing else id-shaped).
  So the data was right and only the **SQL analytics endpoint's cached metadata** was stale -
  fixed with the dedicated `POST .../sqlEndpoints/{id}/refreshMetadata` API
  (`recreateTables: true`, scoped to the 10 gold tables), which returned `Success` for all 10 in
  under 8 seconds; queries were correct immediately after.

**Verified, not just deployed:** every gold fact table's join to its dim(s) on the new BIGINT
keys returns correct, sensible row counts (`fact_cash_call_event`: 1,794 rows join cleanly
across 3 dims, `fact_hse_incidents`: 37 across 2, etc) - checked directly over the SQL endpoint,
not assumed from the notebook completing. Then rebuilt and redeployed the frontend and drove it
with a real headless-browser session (Playwright, not curl): logged in, loaded
`/reconciliation`, `/production`, and `/hse`, and confirmed real partner names ("customer0") and field
names ("Obago") render on the page - i.e. the new JOIN-based queries are actually feeding the UI
correctly, not just returning valid SQL. Zero console/page errors.

## Moved access logs + login allowlist off the Lakehouse onto a real SQL DB (2026-09-07)

Real complaint: the lakehouse-backed access log took up to 5 minutes to become visible (gated by
`nb_ingest_access_logs`'s schedule), and the login allowlist (`dbo.users`, refreshed by `pl_auth`)
took up to 24h. Both are architecturally the same problem - the Lakehouse's SQL analytics endpoint
is read-only, so every write has to go through a batch file-drop + scheduled-notebook path with
real, unavoidable latency. Fixed by giving the webapp a real, writable database of its own.

**`terraform/sql_database.tf`** (new) - `azurerm_mssql_server` + `azurerm_mssql_database`
(Basic tier), **AAD-only authentication** (`azuread_authentication_only = true` - no SQL
login/password exists anywhere on this server). Two real setup steps this needed that aren't
Terraform resources:
1. `CREATE USER ... FROM EXTERNAL PROVIDER` (to grant the app's managed identity DB access) needs
   the *server's own* managed identity to hold the tenant-level Entra `Directory Readers` role, or
   every such statement fails with "Server identity is not configured" - confirmed the hard way,
   including that `WITH OBJECT_ID = '...'` does NOT bypass this requirement (still needs Graph
   lookup access), contrary to what a plausible-sounding blog post suggested. Fixed with
   `frontend/scripts/grant-directory-readers.sh` - a one-time, tenant-admin (Global Administrator)
   action via Microsoft Graph (`directoryRoles` API), same class of manual step as "Service
   principals can use Fabric APIs" for Fabric itself.
2. `frontend/scripts/setup-webapp-db.mjs` (new, idempotent) - runs as the deploy SPN (the SQL
   server's AAD administrator) to grant the app's managed identity `db_datareader`/`db_datawriter`,
   create `dbo.WebAccessLog` and `dbo.AuthorizedUsers`, and seed the two authorized emails.

**`frontend/src/data/access-log.ts`** rewritten: a single `INSERT ... OUTPUT INSERTED.Id` against
`dbo.WebAccessLog` instead of an OneLake file drop - visible immediately, no notebook in the loop
at all anymore. Geo (country/city/continent) is resolved via a single-IP `ip-api.com` call fired
*after* the INSERT and deliberately not awaited by the handler - an in-memory per-IP cache avoids
repeat lookups, and the connection pool is closed by the background task itself once it finishes,
not by the request handler (closing it in the handler's own `finally` would have cancelled the
pending UPDATE - caught this by testing, not by reasoning about it upfront).

**Real bug hit while verifying the geo enrichment**: every stored IP had a `:port` suffix (e.g.
`178.51.4.80:9255`) - Azure App Service appends a port to what `getRequestIP` returns behind its
proxy. `ip-api.com` silently returns nulls for a non-IP string, so geo enrichment failed silently
rather than erroring loudly. Fixed with a small `cleanIp()` helper (handles bare `host:port` and
bracketed IPv6 `[addr]:port`, leaves anything else alone).

**`frontend/src/data/auth-check.ts`** rewritten to query `dbo.AuthorizedUsers` in the new DB
instead of the lakehouse's `dbo.users` - same fail-closed behavior on error, now backed by a
database with no meaningful refresh lag instead of a nightly pipeline.

**Retired**: `nb_ingest_access_logs.Notebook` and its 5-minute schedule - deleted from the repo,
un-scheduled and removed from the live workspace (`cleanup_orphans` handled the removal on
redeploy). `pl_auth`/`nb_get_users`/the rest of the `auth/` folder were left alone - they're a
distinct, still-deferred feature (Power BI report-level access control), not part of this fix.
Also downgraded the app's Fabric workspace role from `Contributor` back to `Viewer`
(`terraform/app_service.tf`) - Contributor was only ever needed for the old OneLake write path;
the app now only reads `gold.*` through the SQL analytics endpoint, same as before Contributor was
added, so it goes back to least-privilege.

**Also**: the "Continue with CUSTOMER0 EntraID" button on `/login` is now visibly disabled (`disabled`
attribute + explanatory `title`) rather than functional - there's no real EntraID tenant behind
it, and leaving it clickable let it act as an unintended, unaudited second login path around the
allowlist.

**Verified end-to-end with real Playwright browser sessions** (not curl - a `page.goto()` per
"navigation" does a full page reload and defeats client-side dwell-time tracking entirely; had to
switch to clicking real in-app `<Link>`s to get a true test): login and page-visit events both
land in `dbo.WebAccessLog` within the same request, correct duration values, clean IPs, resolved
country. Hit the same "deploy completed but the old code is still what's serving" propagation lag
noted earlier in this log on two separate fixes in this pass - each time, waiting for a real `200`
response (not trusting the deployment-API's `complete: true` alone) before testing resolved it.

**`docs/full-rebuild-runbook.md`** (new) - the complete, parametrized CLI sequence to rebuild this
entire stack from a blank subscription: Terraform apply, the two SQL-DB setup steps above,
YAML-model-driven Fabric artifact generation, deploy-mirror sync (including the known stale-file
and stray-pipeline gotchas hit earlier in this log), Fabric deploy, data load (DDL notebook + gold
demo-data generator + SQL-endpoint metadata refresh), and frontend deploy - every command in it
has actually been run this session, not written from memory of what should work.

## Moved the webapp SQL DB off Azure onto a native Fabric SQL Database (2026-09-07)

User feedback after the previous entry: the Azure SQL Database didn't show up in the Fabric portal
(correct - it never was a Fabric item, just an Azure resource the app happened to connect to) and
the ask was explicit - keep it in Fabric, drop Azure. Rebuilt on `fabric_sql_database`, the
Terraform provider's real resource for Fabric's native SQL Database item type (confirmed via
`terraform providers schema -json` against the already-installed provider rather than trusting
scraped docs - the registry page itself wouldn't render for a fetch).

**Confirmed before building anything** (via Microsoft's own docs, not assumed): Admin/Member/
Contributor Fabric workspace roles all get db_owner-equivalent access to *every* SQL database in
the workspace automatically - no `CREATE USER`/`Directory Readers` dance at all, unlike plain
Azure SQL Database. This fully replaced the previous entry's grant script
(`grant-directory-readers.sh`, deleted) and the `CREATE USER ... FROM EXTERNAL PROVIDER` step in
`setup-webapp-db.mjs` (simplified to just table creation/seeding) - both were Azure-SQL-specific
problems that don't exist on this path.

**`terraform/fabric_sql_database.tf`** (new, replaces the deleted `sql_database.tf`) -
`fabric_sql_database.webapp_logs`, `configuration = { creation_mode = "New" }`. App's workspace
role upgraded from Viewer back to Contributor (`terraform/app_service.tf`) - the smallest of the
three roles that includes write. `terraform apply` destroyed the old `azurerm_mssql_server`/
`azurerm_mssql_database`/firewall rules cleanly (4 destroyed, 1 created, 2 changed) - confirmed via
`terraform plan` before applying, no surprises.

**Real gotcha**: the Fabric SQL Database's `properties.server_fqdn` comes back as `"host,1433"`
(classic SQL Server host,port notation) baked into a single string, not split. Passing that whole
string as `mssql`'s `server` option resolves nowhere (`getaddrinfo ENOTFOUND host,1433`) - split it
explicitly and pass `port` separately. Centralized this (and the connection logic generally, which
`access-log.ts` and `auth-check.ts` had duplicated) into a new shared
`frontend/src/data/webapp-db.ts`.

**Real debugging detour, worth recording**: after deploying the fix, logins kept failing with that
exact `ENOTFOUND ...,1433` error for over 20 minutes, across two full redeploys - looked like the
fix wasn't landing. Verified methodically rather than guessing: fetched the live source via Kudu's
VFS API (correct), fetched the *compiled* `.output` bundle actually being served (also correct,
correctly importing the shared helper with the split logic intact), checked the raw app-setting
value byte-for-byte in case of a Unicode lookalike comma (a plain ASCII `,`, nothing exotic). Every
layer checked out. Also learned mid-investigation that `az webapp log deployment list`'s numeric
`status` field is not a reliable success/failure signal by itself - `status: 3` with
`complete: true` turned out to mean the deploy had actually *succeeded* (confirmed via `active:
true` and `last_success_end_time` matching `end_time`), reversing an assumption made earlier in
this same investigation that had triggered an unnecessary redeploy. In the end, with the correct
code confirmed deployed and running, a plain `az webapp restart` immediately fixed it - the running
process was serving stale state well past its own "successful" deploy and container recycle, for
reasons not fully pinned down. Documented as a "if a verified-correct fix still isn't taking
effect, restart before doubting the code" lesson in the runbook, not just here.

**Verified**: `sqldb_webapp_logs` now appears via `GET /v1/workspaces/{id}/items?type=SQLDatabase`
(and so in the Fabric portal) - confirmed directly. A real browser session then confirmed the full
flow again end-to-end on the new database: login and page-visit events land immediately in
`dbo.WebAccessLog`, via the app's managed identity, with zero explicit grant step.

`docs/full-rebuild-runbook.md` updated to match - Phase 1 creates the Fabric SQL Database instead
of an Azure one, Phase 2 drops the grant step entirely, and Phase 8 gets two new notes: the
deployment-status-number caveat, and "restart before doubting the code" if a confirmed-correct fix
still isn't observably live.

## SQL database folder placement + idle-timeout auto-logout (2026-09-07)

Two follow-ups. First, `sqldb_webapp_logs` moved into `data_engineering/webapp_logs` -
`terraform/fabric_sql_database.tf` now creates its own `fabric_folder` under the same
`data_engineering` folder `fabric_lakehouse.tf` already looks up, and sets `folder_id` on the
database resource. Confirmed via schema first that `folder_id` isn't a ForceNew attribute (same
check done for the Lakehouse's own folder move earlier this session) - `terraform apply` came back
as a clean in-place update (1 add, 2 change, 0 destroy), and the database's connection
string/server FQDN/name were unchanged after the move, confirmed from the apply output, so no
app-setting or frontend redeploy was needed for this half.

Second, 30-minute idle auto-logout. Extracted the logout sequence (activity-log entry + SQL-DB
access-log "logout" event + clear session + redirect) out of `app-shell.tsx`'s manual "Log out"
menu item into a shared `frontend/src/hooks/use-logout-with-audit.ts`, so a new
`frontend/src/components/idle-logout.tsx` (mounted alongside `AccessLogTracker`, same
authenticated-only scope) can trigger the identical audited path on a 30-minute inactivity timer
(mouse/keyboard/touch/scroll all reset it) instead of duplicating that sequence.

**Verified as a real functional test, not just a code review** - genuinely necessary given this
session's repeated deploy-propagation-lag findings mean "looks right in the diff" isn't enough
evidence on its own here. Temporarily dropped the timeout to 5 seconds, added mount/fire debug
logging, deployed, and drove it with Playwright: log in, sit truly idle (no synthetic activity)
for 9 seconds, confirm the browser lands back on `/login`. First attempt showed no logout at all -
turned out to be the same stale-container propagation issue from the previous entry, not a bug in
the timer (confirmed by re-running after a proper warm-up wait, which then worked immediately).
Also directly confirmed the resulting `logout (idle timeout)` row landed in `dbo.WebAccessLog`
with the right timestamp. Removed the debug logging and restored the real 30-minute value before
the final deploy - re-verified the normal login/navigation flow still works afterward.

## Key Vault reference stuck on AccessToKeyVaultDenied - abandoned for a plain app setting (2026-09-08)

Added `GROQ_API_KEY` (the AI assistant's LLM key, see `frontend/src/data/assistant.ts`) the "right"
way first: `azurerm_key_vault_secret.groq_api_key` + `azurerm_role_assignment.spark_app_kv_secrets_user`
granting the app's own managed identity "Key Vault Secrets User" on the vault, referenced from
`app_service.tf` as `@Microsoft.KeyVault(SecretUri=...)`. `terraform apply` succeeded cleanly (2
add, 1 change, 0 destroy) and every static check came back correct: role assignment present with
the right principal ID (cross-checked three ways - `az role assignment list`, `terraform state
show` on both the role assignment and the web app's identity block, and `az webapp identity show`
for ground truth), Key Vault network ACLs open (`publicNetworkAccess: Enabled`, no firewall
rules), `keyVaultReferenceIdentity: SystemAssigned` matching the granted principal.

Despite all of that, `GET .../config/configReferences/appsettings` kept reporting
`"status": "AccessToKeyVaultDenied"` for **over 50 minutes**, surviving two full `az webapp
restart`s. Checked the Activity Log for the vault scope for a real error - the only failure event
in that window was a harmless `RoleAssignmentExists` 409 (a redundant `az role assignment create`
retry colliding with itself, same correct role assignment ID both times), not evidence of an
actual permission problem. Every documented cause of this status (wrong principal, network deny,
wrong reference identity) was ruled out directly, which points at RBAC data-plane propagation
itself stalling far past its normal (usually sub-10-minute) window in this tenant - plausibly
related to the same personal-Microsoft-account tenant quirks logged earlier in this file (Fabric
admin UPN handling, `#EXT#` guest-identity representations). Not confirmed as the root cause, just
the best-fit explanation given everything else checked out.

**Fix applied**: gave up on the Key Vault reference and pointed `GROQ_API_KEY` at `var.groq_api_key`
directly as a plain (but still `sensitive = true`, still never committed - `terraform.tfvars` is
gitignored) app setting instead. `terraform apply` (1 change, 0 destroy) took effect immediately -
no propagation delay, since App Service injects app-setting values into `process.env` directly with
no separate resolution step. The Key Vault secret + role assignment resources were left in place
(harmless, not referenced by anything now) in case the RBAC issue is understood later and it's
worth switching back.

If this recurs for a future secret on this tenant: don't assume a fresh `azurerm_role_assignment`
will take effect quickly. Either budget real wait time (well past 10-15 minutes) before treating a
`AccessToKeyVaultDenied` status as a real bug, or default to a plain sensitive app setting for
secrets on this tenant rather than a Key Vault reference.
