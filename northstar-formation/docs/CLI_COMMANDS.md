# Northstar Formation CLI Commands

Quick reference for all available CLI commands.

## Setup

```bash
cd "Unison Insight Services"
```

## Transform Commands

Generate SQL from YAML models.

```bash
# Basic transform with base inheritance
northstar-formation transform models/customers/customer0 --base models/_base -o output/sql

# Transform without base
northstar-formation transform models/customers/customer0 -o output/sql

# With feature overlays
northstar-formation transform models/customers/customer0 --base models/_base --features analytics -o output/sql

# Multiple features
northstar-formation transform models/customers/customer0 --base models/_base --features analytics,gdpr -o output/sql

# Data masking feature
northstar-formation transform models/customers/customer0 --base models/_base --features data_masking -o output/sql

# Transform specific model only
northstar-formation transform models/customers/customer0 --base models/_base --model d_fct_customer -o output/sql

# Transform generate notebooks
northstar-formation transform models/customers/customer0 --base models/_base -o output/ --generate-notebooks



# Dry run (preview without generating files)
northstar-formation transform models/customers/customer0 --base models/_base --dry-run

# Generate notebooks with Fabric logging instrumentation
northstar-formation transform models/customers/customer0 --base models/_base -o output --output-format notebook \
  --enable-logging --logging-project "UnisonInsights-CustomerName"

# Generate notebooks with logging (uses default project name UnisonInsights-{customer})
northstar-formation transform models/customers/customer0 --base models/_base -o output --output-format notebook \ --enable-logging

# Generate regular CTAS notebook with all layers
northstar-formation transform models/customers/customer0 --base models/_base -o output/ --generate-notebooks

# Generate regular CTAS notebook for specific lakehouse and all layers
northstar-formation transform models/customers/customer0 --base models/_base -o output/ --generate-notebooks \
  --ctas-lakehouse lkh_customer0_schema_enabled

# Generate regular CTAS notebook for only gold layer
northstar-formation transform models/customers/customer0 --base models/_base -o output/ --generate-notebooks --layer gold

# Generate regular CTAS notebook for specific lakehouse and only gold layer
northstar-formation transform models/customers/customer0 --base models/_base -o output/ --generate-notebooks \
  --ctas-lakehouse lkh_customer0_schema_enabled --layer gold

# Generate masked CTAS notebooks for specific lakehouses (all layers)
northstar-formation transform models/customers/customer0 --base models/_base -o output/ --generate-notebooks \
  --maskfor lkh_commercial --maskfor lkh_customer0_schema_enabled

# Generate masked CTAS notebooks for only gold layer
northstar-formation transform models/customers/customer0 --base models/_base -o output/ --generate-notebooks \
  --maskfor lkh_commercial --maskfor lkh_customer0_schema_enabled --mask-layer gold

# Generate regular CTAS for gold layer + masked CTAS for silver only
northstar-formation transform models/customers/customer0 --base models/_base -o output/ --generate-notebooks \
  --layer gold --maskfor lkh_commercial --mask-layer silver

# Generate regular CTAS for all layers + masked CTAS for gold only
northstar-formation transform models/customers/customer0 --base models/_base -o output/ --generate-notebooks \
  --maskfor lkh_commercial --mask-layer gold

# Generate regular CTAS for bronze+silver + masked CTAS for gold only
northstar-formation transform models/customers/customer0 --base models/_base -o output/ --generate-notebooks \
  --layer bronze --layer silver --maskfor lkh_commercial --mask-layer gold

# Generate notebooks with explicit default lakehouse and CTAS lakehouse
northstar-formation transform models/customers/customer0 --base models/_base -o output/ --generate-notebooks lkh_customer0_schema_enabled --ctas-lakehouse lkh_customer0_schema_enabled
```

## Validate Commands

Validate YAML models without generating SQL.

```bash
# Validate with base inheritance
northstar-formation validate models/customers/customer0 --base models/_base

# Validate without base
northstar-formation validate models/customers/customer0

# Strict validation (warnings as errors)
northstar-formation validate models/customers/customer0 --base models/_base --strict

# Validate with features
northstar-formation validate models/customers/customer0 --base models/_base --features analytics
```

## Lineage Commands

Generate data lineage graphs.

```bash
# Generate lineage graph (DOT format)
northstar-formation lineage models/customers/customer0 --base models/_base -o output/lineage.dot

# Generate lineage as JSON
northstar-formation lineage models/customers/customer0 --base models/_base --format json -o output/lineage.json

# Lineage without base
northstar-formation lineage models/customers/customer0 -o output/lineage.dot
```

## Pipelines Commands

Generate Microsoft Fabric Data Pipelines from YAML definitions and generated notebooks.

```bash
# Generate pipelines for a customer
northstar-formation pipelines -m models/customers/customer0 -n output/notebooks -p pipelines/customers/customer0 -o output/pipelines -w <workspace-id>
```

## Feature Overlay Tests

Test feature overlay functionality.

```bash
# No features (base model only)
northstar-formation transform models/customers/customer0 --base models/_base -o output/test_no_features

# Analytics feature (adds new columns)
northstar-formation transform models/customers/customer0 --base models/_base --features analytics -o output/test_analytics

# GDPR feature (adds compliance columns)
northstar-formation transform models/customers/customer0 --base models/_base --features gdpr -o output/test_gdpr

# Data masking (modifies existing columns)
northstar-formation transform models/customers/customer0 --base models/_base --features data_masking -o output/test_masking

# Multiple features combined
northstar-formation transform models/customers/customer0 --base models/_base --features analytics,gdpr -o output/test_multi
```

## Verify Output

```bash
# Check generated SQL structure
ls -la output/sql/
ls -la output/sql/bronze/
ls -la output/sql/silver/
ls -la output/sql/gold/

# View a specific generated SQL file
cat output/sql/gold/d_fct_customer.sql
```

## Common Options

| Option | Short | Description |
|--------|-------|-------------|
| `--base` | `-b` | Base models directory for inheritance |
| `--output` | `-o` | Output directory/file path |
| `--features` | | Comma-separated feature flags |
| `--model` | | Transform specific model only |
| `--dry-run` | | Preview without generating files |
| `--strict` | | Treat warnings as errors (validate only) |
| `--format` | | Output format: dot, json (lineage only) |
| `--enable-logging` | | Enable Fabric logging in generated notebooks |
| `--logging-project` | | Logging project name (default: UnisonInsights-{customer}) |
| `--ctas-lakehouse` | | Lakehouse name for the regular CTAS notebook (default: uses logging-project or UnisonInsights-{customer}) |
| `--maskfor` | | Lakehouse names for masked CTAS notebooks (can be specified multiple times) |
| `--layer` | | Specific layer(s) to generate regular CTAS for: bronze, silver, gold (can be specified multiple times, default: all) |
| `--mask-layer` | | Specific layer(s) to generate masked CTAS for: bronze, silver, gold (can be specified multiple times, default: all) |
