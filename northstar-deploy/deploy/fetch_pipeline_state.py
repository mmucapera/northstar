"""Fetch a Fabric DataPipeline's stored definition and print the resolved GUIDs.

Usage:
    py fetch_pipeline_state.py <workspace_id> <pipeline_name>

Uses the same MSAL-silent auth path the deploy uses. Compares each activity's
workspaceId and notebookId against what we expect for the target workspace.
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

# Reuse the deploy's MSAL credential helper
DEPLOY_DIR = Path(r"C:\Users\MMUCAPER\Downloads\00-PRJ\northstar\northstar-deploy\deploy")
sys.path.insert(0, str(DEPLOY_DIR))
from runtime_target_builder import DEFAULT_TENANT, MsalCredential  # type: ignore

import requests


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: py fetch_pipeline_state.py <workspace_id> <pipeline_name>")
        return 2
    workspace_id = sys.argv[1]
    pipeline_name = sys.argv[2]

    cred = MsalCredential(DEFAULT_TENANT)
    token = cred.get_token("https://api.fabric.microsoft.com/.default").token
    hdr = {"Authorization": f"Bearer {token}"}

    # 1) find item id by displayName
    r = requests.get(
        f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items?type=DataPipeline",
        headers=hdr, timeout=30,
    )
    r.raise_for_status()
    items = r.json().get("value", [])
    match = next((i for i in items if i.get("displayName") == pipeline_name), None)
    if not match:
        print(f"pipeline '{pipeline_name}' not found in workspace {workspace_id}")
        print("available:", [i.get("displayName") for i in items])
        return 1
    item_id = match["id"]
    print(f"pipeline item id: {item_id}")

    # 2) get definition (LRO)
    r = requests.post(
        f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items/{item_id}/getDefinition",
        headers=hdr, timeout=30,
    )
    if r.status_code == 202:
        op = r.headers.get("Location")
        while True:
            rr = requests.get(op, headers=hdr, timeout=30)
            rr.raise_for_status()
            s = rr.json().get("status")
            if s == "Succeeded":
                res = requests.get(op + "/result", headers=hdr, timeout=30)
                res.raise_for_status()
                defn = res.json()
                break
            if s == "Failed":
                print("getDefinition failed:", rr.json())
                return 1
    else:
        r.raise_for_status()
        defn = r.json()

    parts = defn.get("definition", {}).get("parts", [])
    content_part = next((p for p in parts if p.get("path") == "pipeline-content.json"), None)
    if not content_part:
        print("no pipeline-content.json part")
        return 1

    payload = base64.b64decode(content_part["payload"]).decode("utf-8")
    doc = json.loads(payload)

    activities = doc.get("properties", {}).get("activities", [])
    print(f"\n=== {pipeline_name} @ workspace {workspace_id} ===")
    print(f"activities: {len(activities)}\n")
    for a in activities:
        tp = a.get("typeProperties", {})
        wsid = tp.get("workspaceId", "-")
        nbid = tp.get("notebookId", "-")
        print(f"  {a['name']:<25} workspaceId={wsid}  notebookId={nbid}")

    # Also list distinct workspaceIds seen
    distinct_ws = sorted({a.get("typeProperties", {}).get("workspaceId") for a in activities if a.get("typeProperties")})
    print(f"\ndistinct workspaceIds referenced: {distinct_ws}")
    print(f"expected target workspace       : {workspace_id}")
    if distinct_ws == [workspace_id]:
        print("→ Fabric-stored state is CORRECT. UI is showing stale cache.")
    else:
        print("→ Fabric-stored state is WRONG. The ghost GUIDs are actually deployed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
