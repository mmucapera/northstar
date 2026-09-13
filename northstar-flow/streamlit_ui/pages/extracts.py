import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

from data.db import require_db
from data import api_client
from components.helpers import status_badge, refresh_button

st.header("Extract Browser")
refresh_button()

db = require_db()

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------

with st.sidebar:
    st.subheader("Filters")

    domains = db.query("SELECT DISTINCT domain_code FROM dbo.extract ORDER BY domain_code")
    domain_opts = ["All"] + [r["domain_code"] for r in domains]
    sel_domain = st.selectbox("Domain", domain_opts, key="ext_domain")

    status_opts = ["All", "NEW", "VALIDATED", "PUSHED", "VALIDATION_FAILED"]
    sel_status = st.selectbox("Status", status_opts, key="ext_status")

    late_only = st.checkbox("Late arrivals only", key="ext_late")

    date_range = st.date_input(
        "Arrived between",
        value=(datetime.now().date() - timedelta(days=7), datetime.now().date()),
        key="ext_dates",
    )

    limit = st.slider("Max results", 10, 500, 100, key="ext_limit")

# ---------------------------------------------------------------------------
# Build query
# ---------------------------------------------------------------------------

conditions = ["1=1"]
params: list = []

if sel_domain != "All":
    conditions.append("e.[domain_code] = ?")
    params.append(sel_domain)

if sel_status != "All":
    conditions.append("e.[status] = ?")
    params.append(sel_status)

if late_only:
    conditions.append("e.[is_late_arrival] = 1")

if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    conditions.append("CAST(e.[arrived_at] AS DATE) >= ?")
    params.append(str(date_range[0]))
    conditions.append("CAST(e.[arrived_at] AS DATE) <= ?")
    params.append(str(date_range[1]))

where = " AND ".join(conditions)

sql = f"""
    SELECT TOP (?)
        e.[extract_id], e.[domain_code], e.[source_code], e.[folder_path],
        e.[period_year], e.[period_month], e.[period_label],
        e.[status], e.[is_latest_for_period], e.[is_late_arrival],
        e.[extraction_date], e.[extraction_def], e.[package_def], e.[cycle_id],
        e.[actual_file_count], e.[total_size_bytes],
        e.[arrived_at], e.[created_at]
    FROM [dbo].[extract] e
    WHERE {where}
    ORDER BY e.[arrived_at] DESC, e.[extract_id] DESC
"""
params.insert(0, limit)
rows = db.query(sql, tuple(params))

# ---------------------------------------------------------------------------
# Results table
# ---------------------------------------------------------------------------

if not rows:
    st.info("No extracts match the current filters.")
    st.stop()

df = pd.DataFrame(rows)
st.caption(f"{len(df)} extract(s) found")

display_cols = [
    "extract_id", "domain_code", "status", "extraction_def", "package_def",
    "extraction_date", "is_late_arrival", "period_label",
    "actual_file_count", "arrived_at",
]
existing_cols = [c for c in display_cols if c in df.columns]

st.dataframe(
    df[existing_cols],
    width="stretch",
    hide_index=True,
    column_config={
        "extract_id": st.column_config.NumberColumn("ID"),
        "domain_code": "Domain",
        "status": "Status",
        "extraction_def": "Extraction Def",
        "package_def": "Package Def",
        "extraction_date": st.column_config.DatetimeColumn("Extraction Date", format="YYYY-MM-DD HH:mm"),
        "is_late_arrival": st.column_config.CheckboxColumn("Late?"),
        "period_label": "Period",
        "actual_file_count": st.column_config.NumberColumn("Files"),
        "arrived_at": st.column_config.DatetimeColumn("Arrived", format="YYYY-MM-DD HH:mm"),
    },
)

# ---------------------------------------------------------------------------
# Detail panel
# ---------------------------------------------------------------------------

st.subheader("Extract Detail")

extract_ids = df["extract_id"].tolist()
sel_id = st.selectbox("Select extract", extract_ids, key="ext_detail_id")

if sel_id:
    detail = db.query_single("SELECT * FROM dbo.extract WHERE extract_id = ?", (sel_id,))
    if detail:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Status**: {status_badge(detail.get('status', ''))}", unsafe_allow_html=True)
            st.text(f"Domain:          {detail.get('domain_code')}")
            st.text(f"Source:          {detail.get('source_code')}")
            st.text(f"Extraction Def:  {detail.get('extraction_def')}")
            st.text(f"Package Def:     {detail.get('package_def')}")
            st.text(f"Cycle ID:        {detail.get('cycle_id')}")
        with col2:
            st.text(f"Period:          {detail.get('period_label')}")
            st.text(f"Extraction Date: {detail.get('extraction_date')}")
            st.text(f"Arrived At:      {detail.get('arrived_at')}")
            st.text(f"Files:           {detail.get('actual_file_count')}")
            st.text(f"Size (bytes):    {detail.get('total_size_bytes')}")
            st.text(f"Late Arrival:    {'Yes' if detail.get('is_late_arrival') else 'No'}")

        # Files
        with st.expander("Extract Files"):
            files = db.query(
                "SELECT file_name, file_format, row_count, file_size_bytes FROM dbo.extract_file WHERE extract_id = ?",
                (sel_id,),
            )
            if files:
                st.dataframe(pd.DataFrame(files), width="stretch", hide_index=True)
            else:
                st.caption("No files registered.")

        # Medallion sync rows
        with st.expander("Medallion Sync Status"):
            syncs = db.query(
                "SELECT sync_id, target_workspace_id, bronze_status, b2s_status, s2g_status, b2s_run_id, s2g_run_id "
                "FROM dbo.medallion_sync WHERE extract_id = ?",
                (sel_id,),
            )
            if syncs:
                st.dataframe(pd.DataFrame(syncs), width="stretch", hide_index=True)
            else:
                st.caption("No sync rows.")

        # Actions
        st.divider()
        act_col1, act_col2 = st.columns(2)
        with act_col1:
            if st.button("🔁 Re-process Extract", key="ext_reprocess"):
                try:
                    resp = api_client.process_extract(sel_id, force=True)
                    st.success(f"Notebook triggered: {resp.get('message', 'OK')}")
                except Exception as exc:
                    st.error(f"Failed: {exc}")
