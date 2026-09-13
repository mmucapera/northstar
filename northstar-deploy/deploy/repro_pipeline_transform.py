"""Reproduce fabric-cicd's pipeline JSON transformations locally, printing intermediate output.

Runs the exact chain (_replace_logical_ids -> _replace_parameters -> _replace_workspace_ids)
against the source customer0 pipeline JSON and shows what would be sent to Fabric.

No network calls. Deployed_items is populated from a live Fabric fetch of the target workspace
so logicalId->guid mapping matches what fabric-cicd would compute during publish.
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from unittest.mock import patch

DEPLOY_DIR = Path(r"C:\Users\MMUCAPER\Downloads\00-PRJ\northstar\northstar-deploy\deploy")
sys.path.insert(0, str(DEPLOY_DIR))
from runtime_target_builder import DEFAULT_TENANT, MsalCredential  # type: ignore
import requests

REPO = Path(r"C:\Users\MMUCAPER\Downloads\00-PRJ\northstar\northstar-formation\output_customer0")
PIPELINE_JSON = REPO / "ENG" / "pipelines" / "PL_BRONZE_FCT_CONFIG.DataPipeline" / "pipeline-content.json"
PARAMETER_FILE = Path(r"C:\Users\MMUCAPER\Downloads\00-PRJ\northstar\northstar-deploy\deploy\parameter.yml")
TARGET_WS = "2349db9d-a206-41d6-bb9b-c134bee74ee0"
ENVIRONMENT = "DEV_C0001_INSIGHTS"


def summarize(label: str, s: str) -> None:
    lines = [l for l in s.splitlines() if "workspaceId" in l or "notebookId" in l]
    print(f"\n--- {label} (first 3 activity refs) ---")
    for l in lines[:6]:
        print(l.strip())


def fetch_deployed_items(token: str, workspace_id: str) -> dict[str, dict]:
    """Return {item_type: {name: guid}}."""
    hdr = {"Authorization": f"Bearer {token}"}
    out: dict[str, dict] = {}
    r = requests.get(
        f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items",
        headers=hdr, timeout=30,
    )
    r.raise_for_status()
    for it in r.json().get("value", []):
        out.setdefault(it["type"], {})[it["displayName"]] = it["id"]
    return out


def main() -> int:
    src = PIPELINE_JSON.read_text(encoding="utf-8")

    from azure.core.credentials import AccessToken, TokenCredential
    from fabric_cicd import FabricWorkspace
    from fabric_cicd._common._item import File, Item

    cred = MsalCredential(DEFAULT_TENANT)
    real_token = cred.get_token("https://api.fabric.microsoft.com/.default").token
    deployed = fetch_deployed_items(real_token, TARGET_WS)
    print(f"Deployed items in workspace {TARGET_WS}:")
    for t, m in deployed.items():
        print(f"  {t}: {len(m)}")

    class FakeCred(TokenCredential):
        def get_token(self, *scopes, **kwargs):
            return AccessToken(real_token, 4102444800)

    # Build FabricWorkspace without hitting Fabric for deployed items refresh
    with patch("fabric_cicd.fabric_workspace.FabricWorkspace._refresh_deployed_items", return_value=None), \
         patch("fabric_cicd.fabric_workspace.FabricWorkspace._refresh_deployed_folders", return_value=None):
        ws = FabricWorkspace(
            workspace_id=TARGET_WS,
            repository_directory=str(REPO),
            item_type_in_scope=["Notebook", "DataPipeline"],
            environment=ENVIRONMENT,
            token_credential=FakeCred(),
            parameter_file_path=str(PARAMETER_FILE),
        )
        ws.deployed_items = {}
        ws.deployed_folders = {}
        # Populate deployed_items map so logicalId lookup can find guids
        # fabric-cicd re-reads .platform files to know logical_id per name.
        ws._refresh_repository_folders()
        ws._refresh_repository_items()
        # For each repo item, set the guid from the deployed map (by displayName)
        for t, items_by_name in ws.repository_items.items():
            for name, item in items_by_name.items():
                guid = deployed.get(t, {}).get(name, "")
                item.guid = guid

    print(f"\nself.workspace_id            = {ws.workspace_id}")
    print(f"self.environment             = {ws.environment}")
    print(f"parameter_file_path          = {ws.parameter_file_path}")
    print(f"environment_parameter keys   = {list(ws.environment_parameter.keys())}")

    # STEP 1: logical ids
    step1 = ws._replace_logical_ids(src)
    summarize("STEP 1 after _replace_logical_ids", step1)

    # STEP 2: parameters (find_replace / key_value)
    item = Item(
        type="DataPipeline", name="PL_BRONZE_FCT_CONFIG", description="", guid="",
        logical_id="", path=Path(PIPELINE_JSON).parent, folder_id="",
    )
    file_obj = File(str(PIPELINE_JSON.parent), PIPELINE_JSON, "text")
    file_obj.contents = step1
    step2 = ws._replace_parameters(file_obj, item)
    summarize("STEP 2 after _replace_parameters", step2)

    # STEP 3: workspace ids
    step3 = ws._replace_workspace_ids(step2)
    summarize("STEP 3 after _replace_workspace_ids (SENT TO FABRIC)", step3)

    print(f"\nexpected workspaceId : {TARGET_WS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
