"""
Export all items from a Microsoft Fabric workspace.

Usage:
    python backup_workspace.py <workspace_id> [--output <folder>] [--tenant <tenant>]
    python backup_workspace.py <workspace_id> --tenant your-tenant.onmicrosoft.com
    python backup_workspace.py <workspace_id> --output ./backup
"""

import argparse
import base64
import json
import time
from pathlib import Path

import requests
from runtime_target_builder import MsalCredential

DEFAULT_TENANT = "unisonfabric.onmicrosoft.com"
SCOPE = "https://api.fabric.microsoft.com/.default"
BASE_URL = "https://api.fabric.microsoft.com/v1"

# Item types that support getDefinition
EXPORTABLE_TYPES = {
    "Notebook",
    "DataPipeline",
    # "SemanticModel",
    # "Report",
    # "Environment",
    # "SparkJobDefinition",
    # "Lakehouse",
}


def get_token(tenant):
    return MsalCredential(tenant).get_token(SCOPE).token


def api_get(token, url):
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    if r.status_code == 404:
        print(f"\nERROR 404: Resource not found at {url}")
        print("This usually means the workspace ID is wrong or you don't have access.")
        r.raise_for_status()
    if r.status_code == 403:
        print(f"\nERROR 403: Access denied for {url}")
        r.raise_for_status()
    r.raise_for_status()
    return r.json()


def api_post(token, url, json_body=None):
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=json_body or {},
    )
    # 200 = immediate response, 202 = long-running operation
    if r.status_code == 202:
        return poll_operation(token, r)
    if r.status_code in (200, 201):
        return r.json() if r.text else {}
    r.raise_for_status()


def poll_operation(token, response):
    """Poll a long-running operation until complete."""
    location = response.headers.get("Location")
    retry_after = int(response.headers.get("Retry-After", 5))

    for _ in range(60):  # max ~5 min
        time.sleep(retry_after)
        r = requests.get(location, headers={"Authorization": f"Bearer {token}"})
        if r.status_code == 200:
            data = r.json()
            status = data.get("status", "")
            if status == "Succeeded":
                # Get the result from the operation
                result_url = response.headers.get("Location")
                result = requests.get(
                    f"{result_url}/result",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if result.status_code == 200:
                    return result.json()
                return data
            elif status == "Failed":
                raise Exception(f"Operation failed: {data}")
        elif r.status_code == 202:
            continue
    raise TimeoutError("Operation timed out")


def list_items(token, workspace_id):
    """List all items in a workspace."""
    url = f"{BASE_URL}/workspaces/{workspace_id}/items"
    items = []
    while url:
        data = api_get(token, url)
        items.extend(data.get("value", []))
        url = data.get("continuationUri")
    return items


def export_item_definition(token, workspace_id, item_id, item_type):
    """Export an item's definition via the REST API."""
    url = f"{BASE_URL}/workspaces/{workspace_id}/items/{item_id}/getDefinition"
    try:
        result = api_post(token, url)
        return result
    except requests.HTTPError as e:
        if e.response.status_code in (400, 404):
            return None  # Item type doesn't support export
        raise


def save_definition(definition, output_dir: Path, item_name: str, item_type: str):
    """Save exported definition parts to disk."""
    item_dir = output_dir / f"{item_name}.{item_type}"
    item_dir.mkdir(parents=True, exist_ok=True)

    parts = definition.get("definition", {}).get("parts", [])
    if not parts:
        return False

    for part in parts:
        path = part.get("path", "content")
        payload = part.get("payload", "")

        # Decode base64 payload
        try:
            content = base64.b64decode(payload)
        except Exception:
            content = payload.encode() if isinstance(payload, str) else payload

        # Create subdirectories if path has them
        file_path = item_dir / path
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write as text if it looks like JSON/text, otherwise binary
        try:
            text = content.decode("utf-8")
            # Pretty-print JSON
            try:
                parsed = json.loads(text)
                text = json.dumps(parsed, indent=2)
            except json.JSONDecodeError:
                pass
            file_path.write_text(text, encoding="utf-8")
        except UnicodeDecodeError:
            file_path.write_bytes(content)

    return True


def main():
    parser = argparse.ArgumentParser(description="Export all items from a Fabric workspace")
    parser.add_argument("workspace_id", help="Fabric workspace GUID")
    parser.add_argument("--output", "-o", default="./workspace_export", help="Output folder")
    parser.add_argument("--tenant", default=DEFAULT_TENANT, help="Azure AD tenant")
    parser.add_argument("--types", "-t", nargs="*", help="Only export these item types")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Authenticating to tenant: {args.tenant}")
    token = get_token(args.tenant)

    print(f"Listing items in workspace: {args.workspace_id}")
    items = list_items(token, args.workspace_id)
    print(f"Found {len(items)} items\n")

    # Save item inventory
    inventory_path = output_dir / "_inventory.json"
    inventory_path.write_text(json.dumps(items, indent=2), encoding="utf-8")

    # Filter by type if requested
    if args.types:
        type_filter = set(args.types)
    else:
        type_filter = EXPORTABLE_TYPES

    exported = 0
    skipped = 0
    failed = 0

    for item in items:
        item_type = item["type"]
        item_name = item["displayName"].replace(" ", "_")
        item_id = item["id"]

        if item_type not in type_filter:
            print(f"  SKIP  {item_type:20} {item_name} (type not exportable)")
            skipped += 1
            continue

        print(f"  EXPORT {item_type:20} {item_name}...", end=" ", flush=True)

        try:
            definition = export_item_definition(token, args.workspace_id, item_id, item_type)
            if definition and save_definition(definition, output_dir, item_name, item_type):
                print("OK")
                exported += 1
            else:
                print("no definition")
                skipped += 1
        except Exception as e:
            print(f"FAILED ({e})")
            failed += 1

    print(f"\nDone: {exported} exported, {skipped} skipped, {failed} failed")
    print(f"Output: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
