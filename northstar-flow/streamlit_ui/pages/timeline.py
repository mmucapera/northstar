import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

from data.db import require_db
from components.helpers import refresh_button

st.header("Pipeline Timeline")
refresh_button()

db = require_db()

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

with st.sidebar:
    st.subheader("Filters")

    domains = db.query("SELECT DISTINCT domain_code FROM dbo.extract ORDER BY domain_code")
    domain_opts = ["All"] + [r["domain_code"] for r in domains]
    sel_domain = st.selectbox("Domain", domain_opts, key="tl_domain")

    workspaces = db.query(
        "SELECT target_workspace_id, target_workspace_name FROM dbo.target_workspace ORDER BY target_workspace_name"
    )
    ws_map = {"All": None}
    ws_map.update({r["target_workspace_name"]: r["target_workspace_id"] for r in workspaces})
    sel_ws = st.selectbox("Workspace", list(ws_map.keys()), key="tl_ws")

    date_range = st.date_input(
        "Date range",
        value=(datetime.now().date() - timedelta(days=7), datetime.now().date()),
        key="tl_dates",
    )

# ---------------------------------------------------------------------------
# Query runs with timestamps
# ---------------------------------------------------------------------------

conditions = ["1=1"]
params: list = []

if sel_domain != "All":
    conditions.append("e.[domain_code] = ?")
    params.append(sel_domain)

if ws_map[sel_ws] is not None:
    conditions.append("ms.[target_workspace_id] = ?")
    params.append(ws_map[sel_ws])

if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    conditions.append("(ms.[b2s_started_at] >= ? OR ms.[s2g_started_at] >= ?)")
    params.extend([str(date_range[0]), str(date_range[0])])
    conditions.append("(ms.[b2s_started_at] <= ? OR ms.[s2g_started_at] <= ?)")
    end_dt = str(date_range[1] + timedelta(days=1))
    params.extend([end_dt, end_dt])

where = " AND ".join(conditions)

sql = f"""
    SELECT
        ms.[sync_id],
        e.[extract_id],
        e.[domain_code],
        tw.[target_workspace_name],
        ms.[b2s_status], ms.[b2s_started_at], ms.[b2s_completed_at], ms.[b2s_run_id],
        ms.[s2g_status], ms.[s2g_started_at], ms.[s2g_completed_at], ms.[s2g_run_id]
    FROM [dbo].[medallion_sync] ms
    INNER JOIN [dbo].[extract] e ON ms.[extract_id] = e.[extract_id]
    INNER JOIN [dbo].[target_workspace] tw ON ms.[target_workspace_id] = tw.[target_workspace_id]
    WHERE {where}
      AND (ms.[b2s_started_at] IS NOT NULL OR ms.[s2g_started_at] IS NOT NULL)
    ORDER BY ms.[b2s_started_at] DESC, ms.[s2g_started_at] DESC
"""
rows = db.query(sql, tuple(params))

if not rows:
    st.info("No pipeline runs found for the selected filters.")
    st.stop()

# ---------------------------------------------------------------------------
# Build Gantt data
# ---------------------------------------------------------------------------

gantt_rows = []
for r in rows:
    label = f"{r['domain_code']} / {r.get('target_workspace_name', '')} (E{r['extract_id']})"

    if r.get("b2s_started_at"):
        gantt_rows.append({
            "Task": label,
            "Phase": "B2S",
            "Status": r.get("b2s_status", "UNKNOWN"),
            "Start": r["b2s_started_at"],
            "End": r.get("b2s_completed_at") or datetime.now(),
            "Run ID": r.get("b2s_run_id", ""),
        })

    if r.get("s2g_started_at"):
        gantt_rows.append({
            "Task": label,
            "Phase": "S2G",
            "Status": r.get("s2g_status", "UNKNOWN"),
            "Start": r["s2g_started_at"],
            "End": r.get("s2g_completed_at") or datetime.now(),
            "Run ID": r.get("s2g_run_id", ""),
        })

if not gantt_rows:
    st.info("No runs with timestamps to display.")
    st.stop()

gantt_df = pd.DataFrame(gantt_rows)
gantt_df["Start"] = pd.to_datetime(gantt_df["Start"])
gantt_df["End"] = pd.to_datetime(gantt_df["End"])

# ---------------------------------------------------------------------------
# Plotly timeline
# ---------------------------------------------------------------------------

STATUS_COLORS = {
    "NOT_STARTED": "#9E9E9E",
    "RUNNING": "#2196F3",
    "SUCCESS": "#4CAF50",
    "FAILED": "#F44336",
    "SKIPPED": "#FF9800",
    "PROCESSING": "#2196F3",
}

fig = px.timeline(
    gantt_df,
    x_start="Start",
    x_end="End",
    y="Task",
    color="Status",
    pattern_shape="Phase",
    color_discrete_map=STATUS_COLORS,
    hover_data=["Phase", "Status", "Run ID"],
)
fig.update_layout(
    height=max(350, len(gantt_df) * 35),
    margin=dict(l=0, r=0, t=30, b=30),
    xaxis_title="Time",
    yaxis_title="",
)
fig.update_yaxes(autorange="reversed")

st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------------------
# Detail table
# ---------------------------------------------------------------------------

st.subheader("Run Details")
st.dataframe(
    gantt_df,
    width="stretch",
    hide_index=True,
    column_config={
        "Task": "Extract",
        "Phase": "Phase",
        "Status": "Status",
        "Start": st.column_config.DatetimeColumn("Started", format="YYYY-MM-DD HH:mm:ss"),
        "End": st.column_config.DatetimeColumn("Ended", format="YYYY-MM-DD HH:mm:ss"),
        "Run ID": "Run ID",
    },
)
