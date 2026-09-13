"""Generate deterministic demo data from customer gold model definitions."""

from __future__ import annotations

import csv
import hashlib
import json
import random
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class GenerationResult:
    """Summary of generated data for one customer."""

    customer: str
    models: int
    rows: int
    output_dir: Path


class DummyDataGenerator:
    """Generate CSV demo data from gold-layer YAML files."""

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed

    def discover_customers(self, customers_dir: Path) -> list[str]:
        """Return customer directory names in stable order."""
        return sorted(path.name for path in customers_dir.iterdir() if path.is_dir())

    def generate_customer(
        self,
        customer_dir: Path,
        output_dir: Path,
        rows: int = 100,
    ) -> GenerationResult:
        """Generate one CSV per gold model and a manifest."""
        if rows < 1:
            raise ValueError("rows must be at least 1")

        if self._is_oil_gas_customer(customer_dir):
            return self._generate_oil_gas_customer(customer_dir.name, output_dir, rows)

        models = self._load_gold_models(customer_dir)
        if not models:
            raise ValueError(f"No gold models found under {customer_dir}")

        customer_output = output_dir / customer_dir.name
        customer_output.mkdir(parents=True, exist_ok=True)
        manifest_models: list[dict[str, Any]] = []

        for model_index, model in enumerate(models):
            model_name = model["name"]
            columns = model["columns"]
            records = [
                {
                    column["name"]: self._value(
                        customer_dir.name,
                        model_name,
                        column,
                        row_index,
                        model_index,
                    )
                    for column in columns
                }
                for row_index in range(rows)
            ]
            output_file = customer_output / f"{self._safe_name(model_name)}.csv"
            self._write_csv(output_file, columns, records)
            manifest_models.append(
                {
                    "model": model_name,
                    "columns": [column["name"] for column in columns],
                    "rows": rows,
                    "file": output_file.name,
                }
            )

        manifest = {
            "customer": customer_dir.name,
            "seed": self.seed,
            "rows_per_model": rows,
            "format": "csv",
            "models": manifest_models,
        }
        (customer_output / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        return GenerationResult(customer_dir.name, len(models), rows * len(models), customer_output)

    def _is_oil_gas_customer(self, customer_dir: Path) -> bool:
        """Detect the inferred oil-and-gas profile from gold model names."""
        model_names = {
            path.stem.lower()
            for path in customer_dir.rglob("*.yaml")
            if path.parent.name.lower() == "gold"
        }
        return {
            "dim_operator",
            "dim_well",
            "dim_refinery",
            "fact_well_daily_metrics",
            "fact_downstream_daily_metrics",
        }.issubset(model_names)

    def _generate_oil_gas_customer(self, customer: str, output_dir: Path, rows: int) -> GenerationResult:
        """Generate correlated upstream and downstream oil-and-gas demo facts."""
        customer_output = output_dir / customer
        customer_output.mkdir(parents=True, exist_ok=True)
        rng = random.Random(self.seed)
        states = ["Alaska", "California", "North Dakota", "Oklahoma", "Wyoming"]
        purposes = ["Oil Production", "Gas Production", "Injection", "Exploration", "Development"]
        statuses = ["Active", "Shut-In", "Suspended", "Abandoned", "Cancelled"]
        operators = [
            {"operator_id": f"{customer.upper()}-OP-{index + 1:02d}", "operator_name": f"{customer.title()} Energy {index + 1}"}
            for index in range(4)
        ]
        wells = []
        for index in range(max(rows, 60)):
            well_id = f"{customer.upper()}-WELL-{index + 1:03d}"
            state = states[index % len(states)]
            purpose = purposes[(index * 3) % len(purposes)]
            status = statuses[(index * 2) % len(statuses)]
            wells.append({
                "well_id": well_id, "operator_id": operators[index % len(operators)]["operator_id"],
                "well_name": f"{state} - {index + 1}", "well_purpose": purpose,
                "operational_status": status, "state_location": state,
            })
        refineries = [
            {"refinery_id": f"{customer.upper()}-REF-{index + 1}", "refinery_name": f"{customer.title()} Refinery {index + 1}"}
            for index in range(4)
        ]
        well_metrics = []
        downstream_metrics = []
        for index in range(max(rows, 60)):
            well = wells[index]
            purpose = well["well_purpose"]
            oil = rng.uniform(1200, 18000) if "Oil" in purpose else rng.uniform(200, 7000)
            gas = rng.uniform(10000, 80000) if "Gas" in purpose else oil * rng.uniform(20, 90)
            well_metrics.append({
                "metric_date": (date(2026, 8, 1) + timedelta(days=index % 28)).isoformat(),
                "well_id": well["well_id"], "water_cut_pct": round(rng.uniform(0.8, 14.0), 1),
                "flaring_venting_mcf": round(rng.uniform(20, 450), 1),
                "co2_emissions_co2e": round(rng.uniform(400, 7200), 1),
                "choke_pct": round(rng.uniform(76, 96), 1),
                "cost_per_boe": round(rng.uniform(0.11, 0.24), 4),
                "well_integrity_index": round(rng.uniform(80, 99), 1),
                "operating_cost": round(rng.uniform(180, 620), 2),
                "flow_pressure_psi": round(rng.uniform(45, 115), 1),
                "oil_production_bbl": round(oil, 1), "gas_production_scf": round(gas, 1),
                "well_uptime_pct": round(rng.uniform(74, 99), 1),
            })
        for month in range(6):
            metric_date = date(2026, 2 + month, 1).isoformat()
            refinery_id = refineries[month % len(refineries)]["refinery_id"]
            throughput = rng.uniform(90, 140)
            revenue = rng.uniform(2.5, 4.2) * 1_000_000_000
            crude_cost = rng.uniform(1.7, 2.8) * 1_000_000_000
            downstream_metrics.append({
                "metric_date": metric_date, "refinery_id": refinery_id,
                "pipeline_throughput_mbpd": round(throughput, 1),
                "carbon_emissions_tco2_per_boe": round(rng.uniform(4.8, 7.2), 2),
                "barrels_processed_m": round(throughput * 1_000_000, 0),
                "quality_compliance_pct": round(rng.uniform(82, 97), 1),
                "refinery_utilization_pct": round(rng.uniform(78, 96), 1),
                "revenue_refined_products_usd": round(revenue, 0),
                "cost_crude_oil_usd": round(crude_cost, 0),
                "refining_margin_usd": round(revenue - crude_cost, 0),
            })

        datasets = {
            "dim_operator": operators, "dim_well": wells, "dim_refinery": refineries,
            "fact_well_daily_metrics": well_metrics,
            "fact_downstream_daily_metrics": downstream_metrics,
        }
        for name, records in datasets.items():
            self._write_records(customer_output / f"{name}.csv", records)
        manifest = {"customer": customer, "profile": "oil_and_gas", "seed": self.seed,
                    "rows_per_well": max(rows, 60), "models": list(datasets)}
        (customer_output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return GenerationResult(customer, len(datasets), sum(len(records) for records in datasets.values()), customer_output)

    def _load_gold_models(self, customer_dir: Path) -> list[dict[str, Any]]:
        models: list[dict[str, Any]] = []
        for model_file in sorted(customer_dir.rglob("*.yaml")):
            if "gold" not in model_file.parts:
                continue
            document = yaml.safe_load(model_file.read_text(encoding="utf-8")) or {}
            model = document.get("model", {})
            if model.get("layer") not in {"gold", "interface"} and "gold" not in model_file.parts:
                continue
            columns = document.get("transformations", {}).get("columns", [])
            if not model.get("name") or not columns:
                continue
            models.append({"name": model["name"], "columns": columns})
        return models

    def _value(
        self,
        customer: str,
        model_name: str,
        column: dict[str, Any],
        row_index: int,
        model_index: int,
    ) -> Any:
        name = str(column["name"])
        lower_name = name.lower()
        data_type = str(column.get("data_type") or "STRING").upper()
        token = self._token(customer, model_name, name, row_index)
        rng = random.Random(self.seed + model_index * 100_003 + row_index)

        if lower_name.endswith("_sk") or lower_name in {"id", "version"}:
            return self._stable_int(token)
        if "timestamp" in lower_name or "datetime" in lower_name or data_type == "TIMESTAMP":
            return (datetime(2026, 1, 1) + timedelta(days=row_index, minutes=model_index)).isoformat(
                sep=" "
            )
        if "date" in lower_name or data_type == "DATE":
            return (date(2026, 1, 1) + timedelta(days=row_index)).isoformat()
        if data_type in {"INT", "INTEGER", "BIGINT", "SMALLINT"}:
            return rng.randint(1, 350)
        if data_type.startswith("DECIMAL") or data_type in {"DOUBLE", "FLOAT", "NUMERIC"}:
            return f"{rng.uniform(1, 1000):.2f}"
        if data_type in {"BOOLEAN", "BOOL"}:
            return row_index % 5 != 0
        if "email" in lower_name:
            return f"demo{row_index + 1}@{customer}.example"
        if "airport" in lower_name or lower_name in {"origin", "destination"}:
            return ["LHR", "AMS", "CDG", "FRA", "JFK", "DXB"][row_index % 6]
        if "country" in lower_name:
            return ["GB", "NL", "FR", "DE", "US"][row_index % 5]
        if "status" in lower_name:
            return ["Active", "In Transit", "Planned", "Completed"][row_index % 4]
        if "type" in lower_name or "category" in lower_name:
            return ["Standard", "Priority", "Critical", "Other"][row_index % 4]
        return f"{customer.upper()}_{self._safe_name(name).upper()}_{row_index + 1:04d}"

    @staticmethod
    def _write_csv(path: Path, columns: list[dict[str, Any]], records: list[dict[str, Any]]) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=[column["name"] for column in columns])
            writer.writeheader()
            writer.writerows(records)

    @staticmethod
    def _write_records(path: Path, records: list[dict[str, Any]]) -> None:
        """Write records with stable field order."""
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)

    @staticmethod
    def _safe_name(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")

    @staticmethod
    def _token(customer: str, model: str, column: str, row: int) -> str:
        return f"{customer}:{model}:{column}:{row}"

    @staticmethod
    def _stable_int(value: str) -> int:
        return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:12], 16)
