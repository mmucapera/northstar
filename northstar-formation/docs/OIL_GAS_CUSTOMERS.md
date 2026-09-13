# Oil and Gas Customer Commands

The CUSTOMER0 and BP model packs use the same supply-chain contract. Run these commands from `northstar-formation` after installing the project:

```bash
source .venv/bin/activate
```

## CUSTOMER0

```bash
northstar-formation transform models/customers/customer0 --base models/_base -o output_customer0/ENG/sql
northstar-formation transform models/customers/customer0 --base models/_base -o output_customer0/ENG/ --generate-notebooks lkh_001 --config-version v1
northstar-formation orphans models/customers/customer0 --base models/_base --mode trace --layer gold --only-missing
northstar-formation check-framework models/customers/customer0 --base models/_base --no-strict --only nok
northstar-formation generate-validation-notebook models/customers/customer0 --base models/_base -o output_customer0/ENG/ --lakehouse-name lkh_001
```

Set the CUSTOMER0 Fabric workspace ID before generating pipelines:

```bash
export CUSTOMER0_WORKSPACE_ID="<customer0-fabric-workspace-id>"
northstar-formation pipelines -m models/customers/customer0 -n output_customer0/ENG/notebooks -p data_pipelines/customers/customer0 -o output_customer0/ENG/pipelines -w "$CUSTOMER0_WORKSPACE_ID"
```

## BP

```bash
northstar-formation transform models/customers/bp --base models/_base -o output_bp/ENG/sql
northstar-formation transform models/customers/bp --base models/_base -o output_bp/ENG/ --generate-notebooks lkh_001 --config-version v1
northstar-formation orphans models/customers/bp --base models/_base --mode trace --layer gold --only-missing
northstar-formation check-framework models/customers/bp --base models/_base --no-strict --only nok
northstar-formation generate-validation-notebook models/customers/bp --base models/_base -o output_bp/ENG/ --lakehouse-name lkh_001
```

Set the BP Fabric workspace ID before generating pipelines:

```bash
export BP_WORKSPACE_ID="<bp-fabric-workspace-id>"
northstar-formation pipelines -m models/customers/bp -n output_bp/ENG/notebooks -p data_pipelines/customers/bp -o output_bp/ENG/pipelines -w "$BP_WORKSPACE_ID"
```

## Model scope

Both customers currently include bronze, silver, and gold models for:

- Facilities and operating sites
- Engineering equipment and design limits
- Suppliers, qualification, and risk score
- Hydrocarbon custody transfers and measurement events

The Neo4j constraints and relationships from the design are a downstream graph projection. They should be added after the relational/Fabric tables have been mapped to the target graph service.
