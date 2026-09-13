import streamlit as st
import pandas as pd
import plotly.express as px

from data.db import require_db
from components.helpers import render_metric_row, refresh_button

st.header("Medallion Pipeline Dashboard")
refresh_button()

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

db = require_db()

domains = db.query("SELECT DISTINCT domain_code FROM dbo.extract ORDER BY domain_code")
domain_options = ["All"] + [r["domain_code"] for r in domains]

workspaces = db.query(
    "SELECT target_workspace_id, target_workspace_name FROM dbo.target_workspace ORDER BY target_workspace_name"
)
ws_map = {r["target_workspace_name"]: r["target_workspace_id"] for r in workspaces}
ws_options = ["All"] + list(ws_map.keys())

col_f1, col_f2 = st.columns(2)
sel_domain = col_f1.selectbox("Domain", domain_options, key="dash_domain")
sel_ws = col_f2.selectbox("Target Workspace", ws_options, key="dash_ws")

domain_filter = None if sel_domain == "All" else sel_domain
ws_filter = None if sel_ws == "All" else ws_map[sel_ws]

# ---------------------------------------------------------------------------
# Dashboard query (reused from medallion.py)
# ---------------------------------------------------------------------------

DASHBOARD_SQL = """
    SELECT
        e.[domain_code],
        ms.[target_workspace_id],
        tw.[target_workspace_name],
        SUM(CASE WHEN ms.[bronze_status] = 'LOADED' THEN 1 ELSE 0 END) AS bronze_loaded,
        SUM(CASE WHEN ms.[b2s_status] = 'NOT_STARTED' THEN 1 ELSE 0 END) AS b2s_not_started,
        SUM(CASE WHEN ms.[b2s_status] = 'RUNNING' THEN 1 ELSE 0 END) AS b2s_running,
        SUM(CASE WHEN ms.[b2s_status] = 'SUCCESS' THEN 1 ELSE 0 END) AS b2s_success,
        SUM(CASE WHEN ms.[b2s_status] = 'FAILED' THEN 1 ELSE 0 END) AS b2s_failed,
        SUM(CASE WHEN ms.[b2s_status] = 'SKIPPED' THEN 1 ELSE 0 END) AS b2s_skipped,
        SUM(CASE WHEN ms.[s2g_status] = 'NOT_STARTED' THEN 1 ELSE 0 END) AS s2g_not_started,
        SUM(CASE WHEN ms.[s2g_status] = 'PROCESSING' THEN 1 ELSE 0 END) AS s2g_processing,
        SUM(CASE WHEN ms.[s2g_status] = 'SUCCESS' THEN 1 ELSE 0 END) AS s2g_success,
        SUM(CASE WHEN ms.[s2g_status] = 'FAILED' THEN 1 ELSE 0 END) AS s2g_failed,
        SUM(CASE WHEN ms.[s2g_status] = 'SKIPPED' THEN 1 ELSE 0 END) AS s2g_skipped,
        SUM(CASE WHEN e.[is_late_arrival] = 1 THEN 1 ELSE 0 END) AS late_arrivals
    FROM [dbo].[medallion_sync] ms
    INNER JOIN [dbo].[extract] e ON ms.[extract_id] = e.[extract_id]
    INNER JOIN [dbo].[target_workspace] tw ON ms.[target_workspace_id] = tw.[target_workspace_id]
    WHERE (? IS NULL OR e.[domain_code] = ?)
      AND (? IS NULL OR ms.[target_workspace_id] = ?)
    GROUP BY e.[domain_code], ms.[target_workspace_id], tw.[target_workspace_name]
    ORDER BY e.[domain_code], tw.[target_workspace_name]
"""

rows = db.query(DASHBOARD_SQL, (domain_filter, domain_filter, ws_filter, ws_filter))

if not rows:
    st.info("No medallion sync data found.")
    st.stop()

df = pd.DataFrame(rows)

# ---------------------------------------------------------------------------
# KPI metrics
# ---------------------------------------------------------------------------

total_syncs = len(df) if df.empty else int(
    df["b2s_not_started"].sum() + df["b2s_running"].sum() + df["b2s_success"].sum()
    + df["b2s_failed"].sum() + df["b2s_skipped"].sum()
)
b2s_ok = int(df["b2s_success"].sum())
s2g_ok = int(df["s2g_success"].sum())
b2s_total = b2s_ok + int(df["b2s_failed"].sum())
s2g_total = s2g_ok + int(df["s2g_failed"].sum())
late = int(df["late_arrivals"].sum())

render_metric_row({
    "Total Sync Rows": (total_syncs, None),
    "B2S Success Rate": (f"{(b2s_ok / b2s_total * 100):.0f}%" if b2s_total else "—", None),
    "S2G Success Rate": (f"{(s2g_ok / s2g_total * 100):.0f}%" if s2g_total else "—", None),
    "Late Arrivals": (late, None),
    "B2S Running": (int(df["b2s_running"].sum()), None),
    "S2G Processing": (int(df["s2g_processing"].sum()), None),
})

# ---------------------------------------------------------------------------
# Status summary table
# ---------------------------------------------------------------------------

st.subheader("Status by Domain & Workspace")
st.dataframe(
    df[[
        "domain_code", "target_workspace_name",
        "bronze_loaded",
        "b2s_not_started", "b2s_running", "b2s_success", "b2s_failed", "b2s_skipped",
        "s2g_not_started", "s2g_processing", "s2g_success", "s2g_failed", "s2g_skipped",
        "late_arrivals",
    ]],
    width="stretch",
    hide_index=True,
    column_config={
        "domain_code": "Domain",
        "target_workspace_name": "Workspace",
        "bronze_loaded": st.column_config.NumberColumn("Bronze"),
        "b2s_not_started": st.column_config.NumberColumn("B2S Pending"),
        "b2s_running": st.column_config.NumberColumn("B2S Running"),
        "b2s_success": st.column_config.NumberColumn("B2S OK"),
        "b2s_failed": st.column_config.NumberColumn("B2S Fail"),
        "b2s_skipped": st.column_config.NumberColumn("B2S Skip"),
        "s2g_not_started": st.column_config.NumberColumn("S2G Pending"),
        "s2g_processing": st.column_config.NumberColumn("S2G Running"),
        "s2g_success": st.column_config.NumberColumn("S2G OK"),
        "s2g_failed": st.column_config.NumberColumn("S2G Fail"),
        "s2g_skipped": st.column_config.NumberColumn("S2G Skip"),
        "late_arrivals": st.column_config.NumberColumn("Late"),
    },
)

# ---------------------------------------------------------------------------
# B2S / S2G stacked bar charts
# ---------------------------------------------------------------------------

st.subheader("B2S Status Distribution")

b2s_melt = df.melt(
    id_vars=["domain_code", "target_workspace_name"],
    value_vars=["b2s_not_started", "b2s_running", "b2s_success", "b2s_failed", "b2s_skipped"],
    var_name="status",
    value_name="count",
)
b2s_melt["status"] = b2s_melt["status"].str.replace("b2s_", "").str.upper()
b2s_melt["label"] = b2s_melt["domain_code"] + " / " + b2s_melt["target_workspace_name"].fillna("")

fig_b2s = px.bar(
    b2s_melt, x="label", y="count", color="status",
    color_discrete_map={"NOT_STARTED": "#9E9E9E", "RUNNING": "#2196F3", "SUCCESS": "#4CAF50", "FAILED": "#F44336", "SKIPPED": "#FF9800"},
    labels={"label": "", "count": "Extracts", "status": "Status"},
)
fig_b2s.update_layout(barmode="stack", height=350, margin=dict(t=10))
st.plotly_chart(fig_b2s, width="stretch")

st.subheader("S2G Status Distribution")

s2g_melt = df.melt(
    id_vars=["domain_code", "target_workspace_name"],
    value_vars=["s2g_not_started", "s2g_processing", "s2g_success", "s2g_failed", "s2g_skipped"],
    var_name="status",
    value_name="count",
)
s2g_melt["status"] = s2g_melt["status"].str.replace("s2g_", "").str.upper()
s2g_melt["label"] = s2g_melt["domain_code"] + " / " + s2g_melt["target_workspace_name"].fillna("")

fig_s2g = px.bar(
    s2g_melt, x="label", y="count", color="status",
    color_discrete_map={"NOT_STARTED": "#9E9E9E", "PROCESSING": "#2196F3", "SUCCESS": "#4CAF50", "FAILED": "#F44336", "SKIPPED": "#FF9800"},
    labels={"label": "", "count": "Extracts", "status": "Status"},
)
fig_s2g.update_layout(barmode="stack", height=350, margin=dict(t=10))
st.plotly_chart(fig_s2g, width="stretch")
