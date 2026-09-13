# Full rebuild runbook: CUSTOMER0 pilot, from a blank Azure subscription to a live webapp

Every command needed to recreate the entire stack from scratch — Fabric workspace, lakehouse,
webapp SQL database (a Fabric SQL Database item, not a separate Azure resource), all Fabric
artifacts (bronze/silver/gold notebooks, pipelines, semantic model), demo data, and the frontend
webapp — and to point the webapp at the result. Written to be
run top-to-bottom against a **brand-new** workspace; each phase also notes what to do if you're
instead pointing an *existing* webapp at a *different* Fabric workspace (a narrower "rewire"
rather than a full rebuild).

Every command here has actually been run this session, in this order, against this exact repo
state — this is not a theoretical sequence.

## Prerequisites (one-time, can't be scripted)

1. **`az login`**, against a subscription that supports Microsoft Fabric capacity. West Europe
   (this runbook's default) is always safe.
2. **A Fabric tenant admin must enable "Service principals can use Fabric APIs"** for the SPN this
   run creates (Fabric Admin Portal → Tenant settings → Developer settings). No API/Terraform
   equivalent — the SPN can't call any Fabric API at all until this is flipped on for it (or a
   security group it belongs to). Do this *after* Phase 1 creates the SPN, *before* Phase 4 (first
   thing that calls the Fabric API as that SPN).

## Phase 1 — Terraform: provision everything

```bash
cd terraform
terraform init -upgrade

# Set customer_id/environment to whatever names this new stack should have -
# a genuinely new workspace normally just means a new `environment` value
# (e.g. "dev2", "uat") so it doesn't collide with an existing deployment
# sharing the same customer_id.
terraform plan \
  -var="customer_id=customer0" \
  -var="environment=dev" \
  -var='admin_object_ids=["you@yourtenant.onmicrosoft.com"]' \
  -out=tfplan
terraform apply "tfplan"
```

This single apply creates: resource group, storage account, Key Vault, Fabric capacity (F2),
Fabric workspace + `lkh_001` Lakehouse (in `data_engineering/lakehouses/`), a `sqldb_webapp_logs`
Fabric SQL Database (in `data_engineering/webapp_logs/` — `fabric_sql_database.tf`, a real
workspace item, visible in the Fabric portal alongside the Lakehouse, not a separate Azure
resource), the deploy SPN
(`northstar-<customer>-<env>-spn`, secret stored in Key Vault, and Admin on the workspace), and the
App Service (Node 22, `node .output/server/index.mjs`, granted Contributor on the workspace —
see app_service.tf).

**Now do prerequisite #2** (tenant admin enables Fabric API access for the new SPN) before
continuing — every command from Phase 3 onward authenticates as this SPN.

Capture the outputs you'll need repeatedly:

```bash
export WORKSPACE_ID=$(terraform output -raw workspace_id)
export LAKEHOUSE_ID=$(terraform output -raw lakehouse_id)
export SQL_ENDPOINT=$(terraform output -raw fabric_sql_endpoint)
export DATABASE_ID=$(terraform output -raw fabric_database_id)
export WEBAPP_SQL_SERVER=$(terraform output -raw webapp_sql_server_fqdn)
export WEBAPP_SQL_DATABASE=$(terraform output -raw webapp_sql_database_name)
export APP_SERVICE_NAME=$(terraform output -raw spark_app_name)
export RESOURCE_GROUP=$(terraform output -raw resource_group_name)
export TENANT_ID=$(terraform output -raw spn_tenant_id)
export CLIENT_ID=$(terraform output -raw spn_client_id)
export CLIENT_SECRET=$(terraform output -raw spn_client_secret)   # sensitive - handle like a password
export AZURE_TENANT_ID=$TENANT_ID AZURE_CLIENT_ID=$CLIENT_ID AZURE_CLIENT_SECRET=$CLIENT_SECRET
```

*Rewire-only variant*: if you're pointing an **existing** webapp at a **different, already-live**
Fabric workspace instead of rebuilding everything, skip straight to
`az webapp config appsettings set --settings FABRIC_SQL_ENDPOINT=... FABRIC_DATABASE_ID=... FABRIC_WORKSPACE_ID=... FABRIC_LAKEHOUSE_ID=...`
against that workspace's real values, then `az webapp restart`. Nothing else in this runbook is
needed for that narrower case.

## Phase 2 — Webapp SQL database: create schema, seed users

No grant step needed here — Admin/Member/Contributor Fabric workspace roles all get
db_owner-equivalent access to every SQL database in the workspace automatically. The deploy SPN
(Admin, from Phase 1) and the App Service's managed identity (Contributor, from Phase 1) both
already have what they need; this just creates the schema:

```bash
cd frontend
export SEED_AUTHORIZED_USERS="mucapera@gmail.com:ALL,brumeto@gmail.com:ALL"
node scripts/setup-webapp-db.mjs
cd ..
```

Idempotent — safe to re-run. Creates `dbo.WebAccessLog` (access logs) and `dbo.AuthorizedUsers`
(login allowlist) with indexes, and seeds the two authorized emails.

*(An earlier version of this stack used a separate Azure SQL Database instead, which needed a
`CREATE USER ... FROM EXTERNAL PROVIDER` step and - because the caller was a service principal -
the SQL server's own managed identity holding the tenant-level `Directory Readers` Entra role just
to resolve that. Moving to a Fabric SQL Database removed all of that - one fewer Azure resource to
manage, and simpler permissions besides.)*

## Phase 3 — Point config at the new workspace

```bash
# northstar-deploy/configurations/customer0/config.yml, core.workspace_id.dev -> $WORKSPACE_ID
python3 - <<EOF
import re
p = "northstar-deploy/configurations/customer0/config.yml"
s = open(p).read()
s = re.sub(r'(dev:\s*)"[0-9a-f-]{36}"', r'\1"$WORKSPACE_ID"', s, count=1)
open(p, "w").write(s)
EOF
```

## Phase 4 — Generate Fabric artifacts from the YAML models

```bash
cd northstar-formation
source .venv/bin/activate   # or: python3 -m venv .venv && pip install -e .

rm -rf output_customer0   # start clean - transform/notebook generation is additive-only into this dir;
                      # stale files from a prior run will linger and get picked up otherwise
                      # (bit this session directly: a rename left duplicate CREATE TABLE
                      # statements in the generated DDL notebook until this was done)

northstar-formation transform models/customers/customer0 --base models/_base -o output_customer0/data_engineering/sql

northstar-formation transform models/customers/customer0 --base models/_base -o output_customer0/data_engineering/ \
  --generate-notebooks lkh_001 \
  --lakehouse-id "$LAKEHOUSE_ID" \
  --lakehouse-workspace-id "$WORKSPACE_ID" \
  --config-version v1

northstar-formation pipelines -m models/customers/customer0 -n output_customer0/data_engineering/notebooks \
  -p data_pipelines/customers/customer0 -o output_customer0/data_engineering/pipelines -w "$WORKSPACE_ID"

northstar-formation semantic-model \
  --models-dir models/customers/customer0 \
  --output output_customer0/data_modelling/semantic_models \
  --name sm_customer0 \
  --sql-endpoint "$SQL_ENDPOINT" \
  --database-id "$DATABASE_ID"
```

## Phase 5 — Sync into the deploy mirror

```bash
DST=../northstar-deploy/configurations/customer0/versions/v1.0.0
rsync -a --delete output_customer0/data_engineering/notebooks/ "$DST/data_engineering/notebooks/"
rsync -a --delete output_customer0/data_engineering/pipelines/ "$DST/data_engineering/pipelines/"
rsync -a --delete output_customer0/data_engineering/demo_data/ "$DST/data_engineering/demo_data/"
rsync -a --delete output_customer0/data_modelling/semantic_models/ "$DST/data_modelling/semantic_models/"
rsync -a --delete output_customer0/auth/ "$DST/auth/"

# northstar-formation pipelines unconditionally copies 00_PRE_ORCH/01_ORCH/DEMO_GENERATOR
# (generic multi-domain master-orchestration pipelines from the shared library) -
# these aren't part of CUSTOMER0's minimal pilot and reference notebooks it doesn't
# have; left in place they make the DataPipeline deploy step fail outright.
rm -rf "$DST/data_engineering/pipelines/00_PRE_ORCH" \
       "$DST/data_engineering/pipelines/01_ORCH" \
       "$DST/data_engineering/pipelines/DEMO_GENERATOR"

cd ..
```

## Phase 6 — Deploy to Fabric

```bash
cd northstar-deploy
source .venv/bin/activate   # or: python3 -m venv .venv && pip install -r requirements.txt

cat > .env <<EOF
TENANT_ID=$TENANT_ID
CLIENT_ID=$CLIENT_ID
CLIENT_SECRET=$CLIENT_SECRET
AZURE_TENANT_ID=$TENANT_ID
AZURE_CLIENT_ID=$CLIENT_ID
AZURE_CLIENT_SECRET=$CLIENT_SECRET
EOF
chmod 600 .env   # gitignored - deploy.py loads it automatically

python deploy.py --customer customer0 --environment dev --mode full --user "$(whoami)"
```

Expect ~95-100 items (Notebooks, DataPipelines, one SemanticModel). If `DataPipeline` deploy fails
with `Failed to publish 5 item(s): ['PL_MASTER_OPR', ...]`, Phase 5's cleanup step didn't run —
remove those three directories and redeploy.

## Phase 7 — Load data

Trigger the DDL notebook (creates every bronze/silver/gold table from the generated SQL) and the
gold demo-data generator (`pl_daily_dummy_data`'s only activity — writes synthetic, FK-linked
star-schema data straight into `gold.*`; bronze/silver stay empty in this pilot, which is fine -
nothing downstream reads them):

```bash
python3 - <<'PYEOF'
import os, requests, time
from azure.identity import ClientSecretCredential

cred = ClientSecretCredential(os.environ["TENANT_ID"], os.environ["CLIENT_ID"], os.environ["CLIENT_SECRET"])
token = cred.get_token("https://api.fabric.microsoft.com/.default").token
H = {"Authorization": f"Bearer {token}"}
WS = os.environ["WORKSPACE_ID"]

items = {it["displayName"]: it["id"] for it in
         requests.get(f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/items?type=Notebook", headers=H).json()["value"]}

def run_and_wait(name, timeout=300):
    item_id = items[name]
    r = requests.post(f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/items/{item_id}/jobs/RunNotebook/instances", headers=H)
    loc = r.headers["Location"]
    start = time.time()
    while time.time() - start < timeout:
        d = requests.get(loc, headers=H).json()
        if d["status"] in ("Completed", "Failed", "Cancelled"):
            print(name, "->", d["status"])
            if d["status"] != "Completed":
                print(d.get("failureReason"))
            return d["status"] == "Completed"
        time.sleep(10)
    print(name, "-> TIMEOUT")
    return False

assert run_and_wait("nb_ddl_customer0")
assert run_and_wait("nb_generate_dummy_gold")
PYEOF
```

Refresh the SQL analytics endpoint's cached metadata for the gold tables (it can lag behind a
schema-changing `CREATE OR REPLACE TABLE` by longer than you'd expect - hit this exact issue this
session):

```bash
python3 - <<'PYEOF'
import os, requests
from azure.identity import ClientSecretCredential

cred = ClientSecretCredential(os.environ["TENANT_ID"], os.environ["CLIENT_ID"], os.environ["CLIENT_SECRET"])
token = cred.get_token("https://api.fabric.microsoft.com/.default").token
H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
WS, SQLEP = os.environ["WORKSPACE_ID"], os.environ["DATABASE_ID"]

body = {"recreateTables": True, "tables": [{"schema": "gold", "tableNames": [
    "dim_partner", "dim_field", "dim_period", "dim_downtime_cause",
    "fact_reconciliation", "fact_production", "fact_downtime",
    "fact_hse_exposure", "fact_hse_incidents", "fact_cash_call_event",
]}]}
r = requests.post(f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/sqlEndpoints/{SQLEP}/refreshMetadata", headers=H, json=body)
print(r.status_code, r.json())
PYEOF
```

*(`pl_auth` - the login-allowlist report-permissions pipeline - and `nb_ingest_access_logs` -
retired: access logs and the login allowlist both live in the webapp's own SQL database now, see
Phase 2, not the lakehouse. Nothing to trigger for either.)*

## Phase 8 — Deploy the frontend

```bash
cd frontend
npm install
npm run build   # local build is just a correctness check - Oryx rebuilds from source server-side
rm -f /tmp/frontend-deploy.zip
git ls-files -z --cached --others --exclude-standard | xargs -0 zip -q /tmp/frontend-deploy.zip
az webapp deploy --resource-group "$RESOURCE_GROUP" --name "$APP_SERVICE_NAME" --src-path /tmp/frontend-deploy.zip --type zip
```

A `504 Gateway Timeout` from the CLI itself is normal for this app (dependency-heavy Oryx build
takes longer than the CLI's own wait) — it does **not** mean the deploy failed. Poll instead:

```bash
until az webapp log deployment list -g "$RESOURCE_GROUP" -n "$APP_SERVICE_NAME" -o json \
  | python3 -c "import json,sys; print(json.load(sys.stdin)[0].get('complete'))" | grep -q True; do
  sleep 20
done
```

Every deploy triggers a container recycle — the first request afterward can take 30-60s to
actually reach the new code (observed repeatedly this session as a false "the fix isn't live"
signal). Wait for a real 200 before testing:

```bash
until curl -s -o /dev/null -w "%{http_code}" "$(terraform -chdir=../terraform output -raw spark_app_url)/" | grep -q 200; do sleep 3; done
```

Two more things observed this session, in case they recur:
- `az webapp deploy`'s own progress numbers are misleading: `status: 3` with `complete: true` can
  mean **success**, not failure - the reliable signals are `active: true` and
  `last_success_end_time` matching `end_time` in `az webapp log deployment list -o json`, not the
  bare status number.
- On one deploy, the container kept serving *stale* code well past a "successful" deployment and
  its own recycle (10+ minutes, past the point curl warm-up checks were passing) - `az webapp
  restart` forced it to pick up the new code immediately. If a fix genuinely isn't showing up after
  a clean deploy and a warm 200, restart before assuming the code itself is wrong.

## Verify

```bash
curl -s -o /dev/null -w "%{http_code}\n" "$(terraform -chdir=terraform output -raw spark_app_url)/login"   # expect 200

# check gold data landed
# (query gold.fact_reconciliation etc. over $SQL_ENDPOINT/$DATABASE_ID via the mssql npm package,
#  same AAD-token pattern as frontend/src/data/fabric-data.ts)

# check the webapp SQL DB is reachable and seeded
# (query dbo.AuthorizedUsers / dbo.WebAccessLog over $WEBAPP_SQL_SERVER/$WEBAPP_SQL_DATABASE)
```

Then load `/login` in a real browser, sign in as one of the seeded authorized emails, and confirm
a row appears in `dbo.WebAccessLog` immediately (no batch/notebook delay - that's the whole point
of Phase 2).
