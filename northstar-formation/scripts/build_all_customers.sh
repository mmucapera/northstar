#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CLI="$PROJECT_DIR/.venv/bin/northstar-formation"

if [[ ! -x "$CLI" ]]; then
    printf 'Missing CLI: %s\n' "$CLI" >&2
    printf 'Create the environment first with:\n' >&2
    printf '  python3 -m venv .venv\n' >&2
    printf '  .venv/bin/python -m pip install .\n' >&2
    exit 1
fi

cd "$PROJECT_DIR"

run_customer() {
    local customer="$1"
    local output="output_${customer}/ENG"

    printf '\n=== %s ===\n' "$customer"
    "$CLI" transform "models/customers/$customer" --base models/_base -o "$output/sql"
    "$CLI" transform "models/customers/$customer" --base models/_base -o "$output/" --generate-notebooks lkh_001 --config-version v1
    local orphan_layer="gold"
    "$CLI" orphans "models/customers/$customer" --base models/_base --mode trace --layer "$orphan_layer" --only-missing
    "$CLI" check-framework "models/customers/$customer" --base models/_base --no-strict --only nok
    "$CLI" generate-validation-notebook "models/customers/$customer" --base models/_base -o "$output/" --lakehouse-name lkh_001

    local pipelines_dir="data_pipelines/customers/$customer"
    if [[ ! -d "$pipelines_dir" ]]; then
        printf 'Skipping pipelines for %s: %s does not exist yet.\n' "$customer" "$pipelines_dir"
        return
    fi

    local workspace_var
    workspace_var="$(printf '%s' "$customer" | tr '[:lower:]' '[:upper:]')_WORKSPACE_ID"
    local workspace_id="${!workspace_var:-}"
    if [[ -z "$workspace_id" ]]; then
        printf 'Missing %s; cannot generate pipelines for %s.\n' "$workspace_var" "$customer" >&2
        return 1
    fi

    "$CLI" pipelines -m "models/customers/$customer" -n "$output/notebooks" -p "$pipelines_dir" -o "$output/pipelines" -w "$workspace_id"
}

while IFS= read -r customer; do
    run_customer "$customer"
done < <(find models/customers -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sort)
