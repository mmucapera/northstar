# Northstar Formation

Production-ready YAML to Spark SQL transformation tool for Microsoft Fabric.

## Installation

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
```

Activate the environment when running commands interactively:

```bash
source .venv/bin/activate
```

## Usage

```bash
northstar-formation transform models/ --output results/
```

Run the complete customer generation workflow on macOS or Linux:

```bash
./scripts/build_all_customers.sh
```

Oil and gas customer commands for CUSTOMER0 and BP are documented in
`docs/OIL_GAS_CUSTOMERS.md`.

Generate deterministic demo CSV data from every customer's gold models:

```bash
northstar-formation generate-dummy-data --rows 100 --seed 42
```

Generate one customer only:

```bash
northstar-formation generate-dummy-data --customer limeflight --rows 250 --output demo_data
```

Each customer gets one CSV per gold model plus a `manifest.json`. New customer folders are discovered automatically.

See the [CLI Reference](docs/CLI_REFERENCE.md) for detailed usage.
