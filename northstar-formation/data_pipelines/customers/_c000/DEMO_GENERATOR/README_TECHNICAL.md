# PL_GOLD_DEMO_GENERATOR

## Overview

This pipeline generates demo/sample data at the Gold layer and exports it as Parquet files. It runs two sequential notebook activities to sample data and then export the results.

## Parameters

| Name | Type | Default Value | Description |
|------|------|---------------|-------------|
| `Customer` | string | `Demo_data` | Target customer name for the export |
| `Sample_percent` | int | `15` | Percentage of data to sample for demo generation |

## Activities

### 1. nb_demo_data_generator

| Property | Value |
|----------|-------|
| Type | TridentNotebook |
| Notebook ID | `bda93a4a-4e0e-9415-439c-3bd1b713da73` |
| Timeout | 12 hours |
| Retry | 0 |
| Depends On | — |

**Parameters passed:**

- `SAMPLE_PERCENT` ← `@pipeline().parameters.Sample_percent` (int)

---

### 2. nb_export_gold_parquet

| Property | Value |
|----------|-------|
| Type | TridentNotebook |
| Notebook ID | `28bc4673-d4cc-859b-412f-94a4490765c0` |
| Timeout | 12 hours |
| Retry | 0 |
| Depends On | `nb_demo_data_generator` (Succeeded) |

**Parameters passed:**

- `customer` ← `@pipeline().parameters.Customer` (string)

## Execution Flow

```
nb_demo_data_generator ──(Success)──► nb_export_gold_parquet
```
