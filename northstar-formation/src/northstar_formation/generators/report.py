"""Self-service Fabric Report (PBIR format) generation, bound live to a
SemanticModel via byConnection (no copy of data, no byPath file coupling -
survives the report and semantic model being redeployed independently).

Deliberately minimal: a handful of native Power BI visuals (cards, a trend
line, a detail table, slicers) users can freely duplicate/extend in the
Fabric portal - this is a starting point for self-service exploration, not a
replica of the custom webapp's UI.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .pipelines import _write_text


class ReportGenError(Exception):
    pass


def _lineage() -> str:
    return str(uuid.uuid4())


def _obj_id() -> str:
    """Fabric/PBIR object names are 20-char hex-ish identifiers by convention -
    any unique string works, but this matches the real-world shape."""
    return uuid.uuid4().hex[:20]


# ---- field reference builders -------------------------------------------

def _column_field(entity: str, prop: str) -> Dict[str, Any]:
    return {
        "Column": {
            "Expression": {"SourceRef": {"Entity": entity}},
            "Property": prop,
        }
    }


def _measure_field(entity: str, prop: str) -> Dict[str, Any]:
    return {
        "Measure": {
            "Expression": {"SourceRef": {"Entity": entity}},
            "Property": prop,
        }
    }


def _projection(field: Dict[str, Any], entity: str, prop: str, display_name: Optional[str] = None) -> Dict[str, Any]:
    p: Dict[str, Any] = {
        "field": field,
        "queryRef": f"{entity}.{prop}",
        "nativeQueryRef": prop,
    }
    if display_name:
        p["displayName"] = display_name
    return p


# ---- visual builders ------------------------------------------------------

def _visual_container(visual_type: str, x: float, y: float, w: float, h: float, query_state: Dict[str, Any], title: Optional[str] = None) -> Dict[str, Any]:
    visual: Dict[str, Any] = {
        "visualType": visual_type,
        "query": {"queryState": query_state},
        "drillFilterOtherVisuals": True,
    }
    if title:
        visual["visualContainerObjects"] = {
            "title": [
                {"properties": {"show": {"expr": {"Literal": {"Value": "true"}}}, "text": {"expr": {"Literal": {"Value": f"'{title}'"}}}}}
            ]
        }
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.4.0/schema.json",
        "name": _obj_id(),
        "position": {"x": x, "y": y, "z": 0, "height": h, "width": w, "tabOrder": 0},
        "visual": visual,
    }


def _card(entity: str, measure: str, x: float, y: float, w: float, h: float, title: str) -> Dict[str, Any]:
    field = _measure_field(entity, measure)
    return _visual_container(
        "cardVisual", x, y, w, h,
        {"Data": {"projections": [_projection(field, entity, measure)]}},
        title=title,
    )


def _slicer(entity: str, column: str, x: float, y: float, w: float, h: float) -> Dict[str, Any]:
    field = _column_field(entity, column)
    return _visual_container(
        "slicer", x, y, w, h,
        {"Values": {"projections": [_projection(field, entity, column)]}},
    )


def _line_chart(category_entity: str, category_col: str, series: List[tuple], x: float, y: float, w: float, h: float, title: str) -> Dict[str, Any]:
    """series: list of (entity, measure_name) tuples plotted on Y."""
    y_projections = [_projection(_measure_field(e, m), e, m) for e, m in series]
    return _visual_container(
        "lineChart", x, y, w, h,
        {
            "Category": {"projections": [_projection(_column_field(category_entity, category_col), category_entity, category_col)]},
            "Y": {"projections": y_projections},
        },
        title=title,
    )


def _table(entity: str, columns: List[str], x: float, y: float, w: float, h: float, title: str) -> Dict[str, Any]:
    projections = [_projection(_column_field(entity, c), entity, c) for c in columns]
    return _visual_container(
        "tableEx", x, y, w, h,
        {"Values": {"projections": projections}},
        title=title,
    )


# ---- top-level definition files -------------------------------------------

def _definition_pbir(semantic_model_id: str) -> str:
    # This exact shape (not the newer "semanticmodelid=..." connectionString
    # form docs also show) is what fabric-cicd's own ReportPublisher builds
    # when it auto-converts a byPath reference (fabric_cicd/_items/_report.py,
    # func_process_file) - i.e. the one path this library actually exercises
    # against real Fabric. Since this report has no local semantic model
    # files to byPath-resolve against, that auto-conversion never fires, so
    # it's hand-authored here to match it exactly rather than trust the
    # newer documented form, which isn't what this library's own tested code
    # path produces.
    return json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/1.0.0/schema.json",
        "version": "4.0",
        "datasetReference": {
            "byConnection": {
                "connectionString": None,
                "pbiServiceModelId": None,
                "pbiModelVirtualServerName": "sobe_wowvirtualserver",
                "pbiModelDatabaseName": semantic_model_id,
                "name": "EntityDataSource",
                "connectionType": "pbiServiceXmlaStyleLive",
            }
        },
    }, indent=2)


def _version_json() -> str:
    return json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
        "version": "2.0.0",
    }, indent=2)


def _report_json() -> str:
    # themeCollection.baseTheme is required by the report schema (publish
    # fails with "Required properties are missing: themeCollection"
    # otherwise) - references a real built-in Power BI base theme, paired
    # with the matching resourcePackages entry every real exported report.json
    # carries for it.
    return json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.0.0/schema.json",
        "themeCollection": {
            "baseTheme": {
                "name": "CY24SU10",
                "reportVersionAtImport": {"visual": "1.8.95", "report": "2.0.95", "page": "1.3.95"},
                "type": "SharedResources",
            }
        },
        "resourcePackages": [
            {
                "name": "SharedResources",
                "type": "SharedResources",
                "items": [{"name": "CY24SU10", "path": "BaseThemes/CY24SU10.json", "type": "BaseTheme"}],
            }
        ],
        "settings": {
            "useStylableVisualContainerHeader": True,
            "exportDataMode": "AllowSummarized",
        },
    }, indent=2)


def _pages_json(page_names: List[str]) -> str:
    return json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json",
        "pageOrder": page_names,
        "activePageName": page_names[0],
    }, indent=2)


def _page_json(name: str, display_name: str) -> str:
    return json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.0.0/schema.json",
        "name": name,
        "displayName": display_name,
        "displayOption": "FitToPage",
        "height": 720,
        "width": 1280,
    }, indent=2)


def _platform_json(display_name: str, logical_id: str) -> str:
    return json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Report", "displayName": display_name},
        "config": {"version": "2.0", "logicalId": logical_id},
    }, indent=2)


def generate_self_service_report(
    output_dir: Path,
    report_name: str,
    semantic_model_id: str,
    logical_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a minimal self-service Report bound live (byConnection) to
    an existing SemanticModel - no data copy, works regardless of where the
    semantic model's own files live or get redeployed.

    Layout (single "Overview" page, 1280x720): 4 KPI cards top, a period/
    partner slicer pair on the left, a variance trend line chart and a
    reconciliation detail table below - a small, real starting point users
    can duplicate pages/visuals from rather than a finished dashboard.
    """
    rpt_dir = output_dir / f"{report_name}.Report"
    def_dir = rpt_dir / "definition"
    page_id = _obj_id()
    page_dir = def_dir / "pages" / "Overview.Page"
    visuals_dir = page_dir / "visuals"
    visuals_dir.mkdir(parents=True, exist_ok=True)

    _write_text(rpt_dir / "definition.pbir", _definition_pbir(semantic_model_id))
    _write_text(
        rpt_dir / ".platform",
        _platform_json(report_name, logical_id or str(uuid.uuid5(uuid.NAMESPACE_DNS, report_name.strip().lower()))),
    )
    _write_text(def_dir / "version.json", _version_json())
    _write_text(def_dir / "report.json", _report_json())
    _write_text(def_dir / "pages" / "pages.json", _pages_json([page_id]))
    _write_text(page_dir / "page.json", _page_json(page_id, "Overview"))

    visuals = {
        "CardAllocated": _card("fact_reconciliation", "Total Allocated Bbl", 220, 0, 250, 120, "Total Allocated (bbl)"),
        "CardLifted": _card("fact_reconciliation", "Total Lifted Bbl", 480, 0, 250, 120, "Total Lifted (bbl)"),
        "CardVariance": _card("fact_reconciliation", "Avg Variance Pct", 740, 0, 250, 120, "Avg Variance %"),
        "CardProduction": _card("fact_production", "Total Actual Bopd", 1000, 0, 260, 120, "Total Actual (bopd)"),
        "SlicerPeriod": _slicer("dim_period", "Label", 0, 0, 200, 340),
        "SlicerPartner": _slicer("dim_partner", "PartnerName", 0, 360, 200, 340),
        "TrendChart": _line_chart(
            "dim_period", "PeriodId",
            [("fact_reconciliation", "Total Allocated Bbl"), ("fact_reconciliation", "Total Lifted Bbl")],
            220, 140, 510, 280, "Allocated vs. Lifted by Period",
        ),
        "ReconciliationTable": _table(
            "fact_reconciliation",
            ["PeriodId", "PartnerId", "FieldId", "AllocatedBbl", "LiftedBbl", "VariancePct", "Flag", "CashCallStatus"],
            750, 140, 500, 280, "Reconciliation Detail",
        ),
    }
    for visual_name, content in visuals.items():
        v_dir = visuals_dir / f"{visual_name}.Visual"
        v_dir.mkdir(parents=True, exist_ok=True)
        _write_text(v_dir / "visual.json", json.dumps(content, indent=2))

    return {
        "output_dir": str(rpt_dir),
        "page": "Overview",
        "visuals": list(visuals.keys()),
    }
