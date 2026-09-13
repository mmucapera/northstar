# Multi-Tenant Streamlit Dashboard Plan

## Context

The Streamlit UI is currently hardwired to a single northstar-flow backend (`INS_ORCH_API_URL` + `INS_ORCH_API_KEY`) and a single Fabric SQL database (`INS_ORCH_SQL_ENDPOINT` + `INS_ORCH_DATABASE`). The goal is to support multiple customers, each with their own orchestrator environment, selectable from a single shared dashboard.

## Architecture

Each customer has their **own northstar-flow API deployment** (separate App Service, separate DB). The Streamlit app is a **single shared dashboard** that switches which backend it talks to based on user selection.

- Tenant isolation is at the infrastructure level (separate APIs, separate DBs)
- The Streamlit app is stateless — it just switches which backend it talks to
- No risk of data leakage between tenants
- Each customer's orchestrator has its own ADLS sources, pipelines, etc.

## 1. Environment Config File — `environments.yaml`

```yaml
environments:
  - id: "customer-a"
    label: "Customer A — Production"
    api_url: "https://customer-a-orch.azurewebsites.net"
    api_key: "${CUST_A_API_KEY}"
    sql_endpoint: "customer-a-endpoint.database.fabric.microsoft.com"
    database: "northstar_control_cust_a"
    azure_tenant_id: "${AZURE_TENANT_ID}"
    azure_client_id: "${AZURE_CLIENT_ID}"
    azure_client_secret: "${AZURE_CLIENT_SECRET}"

  - id: "customer-b"
    label: "Customer B — Production"
    api_url: "https://customer-b-orch.azurewebsites.net"
    api_key: "${CUST_B_API_KEY}"
    sql_endpoint: "customer-b-endpoint.database.fabric.microsoft.com"
    database: "northstar_control_cust_b"
    azure_tenant_id: "${AZURE_TENANT_ID}"
    azure_client_id: "${AZURE_CLIENT_ID}"
    azure_client_secret: "${AZURE_CLIENT_SECRET}"
```

SAS tokens / API keys stay in env vars via `${ENV_VAR}` interpolation. The YAML never contains raw secrets.

Backwards compatibility: if `environments.yaml` doesn't exist, fall back to the current flat env vars as a single "default" environment.

## 2. Environment Selector in Sidebar

A dropdown at the top of the sidebar (in `app.py`), stored in `st.session_state["active_env"]`. Switching environments re-wires both the API client and DB connection.

## 3. Dynamic API Client + DB

### api_client.py

Instead of `_base_url()` returning a static env var, it reads from `st.session_state["active_env"]`. The `_headers()` function similarly reads the active environment's API key.

### db.py

The `@st.cache_resource` DB connection gets keyed by environment ID, so each tenant has its own cached connection. Switching environments creates/reuses a separate connection.

## Files to modify

| File | Change |
|------|--------|
| `app.py` | Load environments, render selector in sidebar, store in session state |
| `data/api_client.py` | Read base URL + API key from active environment |
| `data/db.py` | Key DB connection by environment, read credentials from active env |
| `environments.yaml` | New config file (gitignored) |
| `environments.yaml.example` | New example template (tracked) |

## Implementation Order

1. Create environment config model + YAML loader (reuse `${ENV_VAR}` interpolation from `config.py`)
2. Add environment selector to `app.py` sidebar
3. Refactor `api_client.py` to read from active environment
4. Refactor `db.py` to key connections by environment
5. Create `environments.yaml.example`
6. Add `environments.yaml` to `.gitignore`
