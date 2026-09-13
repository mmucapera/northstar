#!/usr/bin/env bash
# Pause/resume the Fabric capacity for a customer/environment without
# touching Terraform state - pause/resume is a runtime action on the Azure
# resource, not a Terraform-managed property, so `terraform apply` has
# nothing to do with this. See terraform/README.md for when to use this.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

usage() {
    printf 'Usage: %s <pause|resume|status>\n' "$(basename "$0")" >&2
    printf 'Run from an environment where `terraform output` works (state must be initialized).\n' >&2
    exit 1
}

[[ $# -eq 1 ]] || usage
action="$1"

cd "$TERRAFORM_DIR"

capacity_id="$(terraform output -raw fabric_capacity_id 2>/dev/null || true)"
if [[ -z "$capacity_id" ]]; then
    printf 'Could not read fabric_capacity_id from terraform output.\n' >&2
    printf 'Run `terraform apply` first, or check outputs.tf exposes it.\n' >&2
    exit 1
fi

case "$action" in
    pause)
        az resource invoke-action --action suspend --ids "$capacity_id"
        ;;
    resume)
        az resource invoke-action --action resume --ids "$capacity_id"
        ;;
    status)
        az resource show --ids "$capacity_id" --query "properties.state" -o tsv
        exit 0
        ;;
    *)
        usage
        ;;
esac

printf 'Waiting for state change...\n'
sleep 8
az resource show --ids "$capacity_id" --query "properties.state" -o tsv
