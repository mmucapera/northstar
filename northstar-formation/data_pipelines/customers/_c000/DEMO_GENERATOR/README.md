# Demo Data Recipients

## Purpose

**Anonymized, sampled** exports of the Gold layer intended for external parties who need to evaluate or demo the Insights platform without access to real production data.

## What is shared

- A **ZIP archive** of Parquet files (`{demo_data}_gold_export_{YYYYMMDD}.zip`) from gold medallion layer.

## Data Protection Applied

| Protection | Detail |
|------------|--------|
| Sampling | Only a configurable percentage (default 15%) of seed dimensions is included |
| Masking | Sensitive identifiers (Customer, Product, Location, Machine, Process IDs) are hashed|
| Filtering | Fact tables are scoped to only the sampled dimension keys;
| Renaming | Select column values are relabelled to generic names (e.g. forecast group names) |
