import streamlit as st
import pandas as pd

from data.db import require_db
from components.helpers import refresh_button

st.header("Push Jobs")
refresh_button()

db = require_db()

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

with st.sidebar:
    st.subheader("Filters")

    status_opts = ["All", "PENDING", "RUNNING", "SUCCESS", "FAILED", "PARTIAL", "CANCELLED", "RECALLED"]
    sel_status = st.selectbox("Status", status_opts, key="pj_status")

    sel_extract_id = st.text_input("Extract ID", key="pj_eid")

    workspaces = db.query(
        "SELECT target_workspace_id, target_workspace_name FROM dbo.target_workspace ORDER BY target_workspace_name"
    )
    ws_map = {"All": None}
    ws_map.update({r["target_workspace_name"]: r["target_workspace_id"] for r in workspaces})
    sel_ws = st.selectbox("Target Workspace", list(ws_map.keys()), key="pj_ws")

    limit = st.slider("Max results", 10, 500, 100, key="pj_limit")

# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

conditions = ["1=1"]
params: list = []

if sel_status != "All":
    conditions.append("pj.[status] = ?")
    params.append(sel_status)

if sel_extract_id.strip():
    conditions.append("pj.[extract_id] = ?")
    params.append(int(sel_extract_id))

if ws_map[sel_ws] is not None:
    conditions.append("pj.[target_workspace_id] = ?")
    params.append(ws_map[sel_ws])

where = " AND ".join(conditions)

sql = f"""
    SELECT TOP (?)
        pj.[push_job_id], pj.[extract_id],
        e.[domain_code],
        pj.[target_workspace_name],
        pj.[status],
        pj.[started_at], pj.[completed_at], pj.[duration_seconds],
        pj.[files_attempted], pj.[files_succeeded], pj.[files_failed],
        pj.[bytes_transferred],
        pj.[error_message],
        pj.[attempt_number], pj.[max_attempts]
    FROM [dbo].[push_job] pj
    INNER JOIN [dbo].[extract] e ON pj.[extract_id] = e.[extract_id]
    WHERE {where}
    ORDER BY pj.[created_at] DESC
"""
params.insert(0, limit)
rows = db.query(sql, tuple(params))

# ---------------------------------------------------------------------------
# Summary metrics
# ---------------------------------------------------------------------------

if rows:
    df = pd.DataFrame(rows)
    status_counts = df["status"].value_counts()

    metric_cols = st.columns(5)
    for i, s in enumerate(["PENDING", "RUNNING", "SUCCESS", "FAILED", "PARTIAL"]):
        metric_cols[i].metric(s, int(status_counts.get(s, 0)))

    # Table
    st.subheader("Push Job Details")
    st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        column_config={
            "push_job_id": st.column_config.NumberColumn("Job ID"),
            "extract_id": st.column_config.NumberColumn("Extract"),
            "domain_code": "Domain",
            "target_workspace_name": "Workspace",
            "status": "Status",
            "started_at": st.column_config.DatetimeColumn("Started", format="YYYY-MM-DD HH:mm"),
            "completed_at": st.column_config.DatetimeColumn("Completed", format="YYYY-MM-DD HH:mm"),
            "duration_seconds": st.column_config.NumberColumn("Duration (s)"),
            "files_attempted": st.column_config.NumberColumn("Attempted"),
            "files_succeeded": st.column_config.NumberColumn("Succeeded"),
            "files_failed": st.column_config.NumberColumn("Failed"),
            "bytes_transferred": st.column_config.NumberColumn("Bytes"),
            "error_message": "Error",
            "attempt_number": st.column_config.NumberColumn("Attempt"),
            "max_attempts": st.column_config.NumberColumn("Max"),
        },
    )
else:
    st.info("No push jobs match the current filters.")
