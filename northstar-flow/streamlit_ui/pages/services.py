import streamlit as st

from data import api_client
from components.helpers import refresh_button

st.header("Service Controls")
refresh_button()

col_poller, col_orch = st.columns(2)

# ---------------------------------------------------------------------------
# ADLS Poller card
# ---------------------------------------------------------------------------

with col_poller:
    st.subheader("ADLS Poller")
    try:
        ps = api_client.get_poller_status()
    except Exception as exc:
        st.error(f"API unreachable: {exc}")
        ps = {}

    running = ps.get("is_running", False)
    st.metric("Status", "Running" if running else "Stopped")

    m1, m2 = st.columns(2)
    m1.metric("Poll Cycles", ps.get("poll_cycles", 0))
    m2.metric("Files Detected", ps.get("new_files_detected", 0))

    m3, m4 = st.columns(2)
    m3.metric("Errors", ps.get("errors", 0))
    m4.metric("Elapsed (s)", f"{ps.get('elapsed_seconds', 0):.0f}")

    st.caption(f"Started: {ps.get('started_at', '—')}")
    st.caption(f"Last poll: {ps.get('last_poll_at', '—')}")

    # Per-source sub-list
    try:
        sources = api_client.get_poller_sources()
    except Exception:
        sources = []

    if len(sources) > 1:
        st.caption("**Sources:**")
        for src in sources:
            icon = "🟢" if src.get("is_running") else "⚪"
            st.caption(f"{icon} {src['source_id']} — {src.get('label', '')}")

    b1, b2 = st.columns(2)
    with b1:
        if st.button("▶ Start", disabled=running, key="svc_poller_start"):
            try:
                api_client.start_poller()
                st.success("Poller(s) started.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    with b2:
        if st.button("⏹ Stop", disabled=not running, key="svc_poller_stop"):
            try:
                api_client.stop_poller()
                st.success("Poller(s) stopped.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

# ---------------------------------------------------------------------------
# Medallion Orchestrator card
# ---------------------------------------------------------------------------

with col_orch:
    st.subheader("Medallion Orchestrator")
    try:
        os_ = api_client.get_orchestrator_status()
    except Exception as exc:
        st.error(f"API unreachable: {exc}")
        os_ = {}

    orch_running = os_.get("is_running", False)
    st.metric("Status", "Running" if orch_running else "Stopped")

    m1, m2 = st.columns(2)
    m1.metric("Scan Cycles", os_.get("scan_cycles", 0))
    m2.metric("Errors", os_.get("errors", 0))

    m3, m4 = st.columns(2)
    m3.metric("B2S Triggered", os_.get("b2s_triggered", 0))
    m4.metric("B2S Completed", os_.get("b2s_completed", 0))

    m5, m6 = st.columns(2)
    m5.metric("S2G Triggered", os_.get("s2g_triggered", 0))
    m6.metric("S2G Completed", os_.get("s2g_completed", 0))

    m7, m8 = st.columns(2)
    m7.metric("Active B2S Jobs", os_.get("active_b2s_jobs", 0))
    m8.metric("Active S2G Jobs", os_.get("active_s2g_jobs", 0))

    st.caption(f"Grace period: {os_.get('grace_period_minutes', '—')} min")
    st.caption(f"Pipeline poll interval: {os_.get('pipeline_poll_interval_seconds', '—')} s")
    st.caption(f"Scan interval (from config): {os_.get('scan_interval', '—')}")
    st.caption(f"Started: {os_.get('started_at', '—')}")
    st.caption(f"Last scan: {os_.get('last_scan_at', '—')}")

    b1, b2 = st.columns(2)
    with b1:
        if st.button("▶ Start", disabled=orch_running, key="svc_orch_start"):
            try:
                api_client.start_orchestrator()
                st.success("Orchestrator started.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    with b2:
        if st.button("⏹ Stop", disabled=not orch_running, key="svc_orch_stop"):
            try:
                api_client.stop_orchestrator()
                st.success("Orchestrator stopped.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
