import streamlit as st
import pandas as pd

from data.db import require_db
from data import api_client
from components.helpers import status_badge, refresh_button

st.header("Late Arrival Manager")
refresh_button()

db = require_db()

# ---------------------------------------------------------------------------
# Late arrival extracts
# ---------------------------------------------------------------------------

LATE_SQL = """
    SELECT
        e.[extract_id], e.[domain_code], e.[extraction_def], e.[package_def],
        e.[extraction_date], e.[arrived_at], e.[status],
        e.[is_late_arrival]
    FROM [dbo].[extract] e
    WHERE e.[is_late_arrival] = 1
    ORDER BY e.[domain_code], e.[package_def], e.[extraction_date]
"""
late_rows = db.query(LATE_SQL)

if not late_rows:
    st.success("No late arrivals detected.")
    st.stop()

df = pd.DataFrame(late_rows)

# ---------------------------------------------------------------------------
# Summary by batch (domain + extraction_def + package_def)
# ---------------------------------------------------------------------------

st.subheader("Late Arrival Batches")

batch_df = (
    df.groupby(["domain_code", "extraction_def", "package_def"])
    .agg(
        count=("extract_id", "count"),
        earliest=("extraction_date", "min"),
        latest=("extraction_date", "max"),
    )
    .reset_index()
)

st.dataframe(
    batch_df,
    width="stretch",
    hide_index=True,
    column_config={
        "domain_code": "Domain",
        "extraction_def": "Extraction Def",
        "package_def": "Package Def",
        "count": st.column_config.NumberColumn("Late Extracts"),
        "earliest": st.column_config.DatetimeColumn("Earliest", format="YYYY-MM-DD HH:mm"),
        "latest": st.column_config.DatetimeColumn("Latest", format="YYYY-MM-DD HH:mm"),
    },
)

# ---------------------------------------------------------------------------
# Detail table of all flagged extracts
# ---------------------------------------------------------------------------

with st.expander("All Late Arrival Extracts", expanded=True):
    st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        column_config={
            "extract_id": st.column_config.NumberColumn("ID"),
            "domain_code": "Domain",
            "extraction_def": "Extraction Def",
            "package_def": "Package Def",
            "extraction_date": st.column_config.DatetimeColumn("Extraction Date", format="YYYY-MM-DD HH:mm"),
            "arrived_at": st.column_config.DatetimeColumn("Arrived", format="YYYY-MM-DD HH:mm"),
            "status": "Status",
            "is_late_arrival": st.column_config.CheckboxColumn("Late?"),
        },
    )

# ---------------------------------------------------------------------------
# Blocker extracts — what already processed past these late arrivals
# ---------------------------------------------------------------------------

st.subheader("Blocking Extracts")
st.caption("Extracts with a later extraction_date that already completed B2S, causing the late arrival flag.")

BLOCKER_SQL = """
    SELECT DISTINCT
        blocker.[extract_id] AS blocker_id,
        blocker.[domain_code],
        blocker.[extraction_def],
        blocker.[package_def],
        blocker.[extraction_date] AS blocker_extraction_date,
        ms.[b2s_status],
        late.[extract_id] AS late_extract_id,
        late.[extraction_date] AS late_extraction_date
    FROM [dbo].[extract] late
    INNER JOIN [dbo].[extract] blocker
        ON blocker.[domain_code] = late.[domain_code]
       AND (blocker.[package_def] = late.[package_def] OR (blocker.[package_def] IS NULL AND late.[package_def] IS NULL))
       AND (blocker.[extraction_def] = late.[extraction_def] OR (blocker.[extraction_def] IS NULL AND late.[extraction_def] IS NULL))
       AND blocker.[extraction_date] > late.[extraction_date]
    INNER JOIN [dbo].[medallion_sync] ms
        ON ms.[extract_id] = blocker.[extract_id]
       AND ms.[b2s_status] IN ('RUNNING', 'SUCCESS', 'FAILED')
    WHERE late.[is_late_arrival] = 1
    ORDER BY blocker.[domain_code], blocker.[package_def], blocker.[extraction_date]
"""
blockers = db.query(BLOCKER_SQL)
if blockers:
    st.dataframe(pd.DataFrame(blockers), width="stretch", hide_index=True)
else:
    st.caption("No blocker details found.")

# ---------------------------------------------------------------------------
# Batch Rerun form
# ---------------------------------------------------------------------------

st.subheader("Batch Rerun")
st.markdown(
    "**Skip** (`lookback = 0`): discard the late arrival — mark as SKIPPED, unblock S2G.  \n"
    "**Replay** (`lookback > 0`): reset B2S/S2G for the late arrival and all extracts within the lookback window."
)

with st.form("batch_rerun_form"):
    domain_vals = sorted(df["domain_code"].unique())
    form_domain = st.selectbox("Domain Code", domain_vals, key="br_domain")

    form_package = st.text_input("Package Def (optional)", key="br_pkg")

    form_extraction_def = st.text_input("Extraction Def (optional)", key="br_extdef")

    form_lookback = st.number_input(
        "Lookback Hours (0 = skip/discard, >0 = replay window)",
        min_value=0, max_value=720, value=0, step=1, key="br_lookback",
    )

    form_ws = st.text_input("Target Workspace ID (optional)", key="br_ws")

    submitted = st.form_submit_button("Execute Batch Rerun")

if submitted:
    try:
        resp = api_client.batch_rerun(
            domain_code=form_domain,
            lookback_hours=form_lookback,
            package_def=form_package or None,
            extraction_def=form_extraction_def or None,
            target_workspace_id=form_ws or None,
        )
        if form_lookback == 0:
            st.success(
                f"Skipped: {resp.get('extracts_reset', 0)} extract(s), "
                f"{resp.get('syncs_reset', 0)} sync row(s) marked SKIPPED."
            )
        else:
            st.success(
                f"Replay initiated: {resp.get('extracts_reset', 0)} extract(s), "
                f"{resp.get('syncs_reset', 0)} sync row(s) reset to NOT_STARTED."
            )
        affected = resp.get("affected_extracts", [])
        if affected:
            st.dataframe(pd.DataFrame(affected), width="stretch", hide_index=True)
    except Exception as exc:
        st.error(f"Batch rerun failed: {exc}")
