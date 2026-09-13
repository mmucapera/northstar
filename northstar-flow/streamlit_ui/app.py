import streamlit as st

st.set_page_config(
    page_title="INS Orchestrator",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

dashboard = st.Page("pages/dashboard.py", title="Dashboard", icon="📊", default=True)
extracts = st.Page("pages/extracts.py", title="Extracts", icon="📦")
push_jobs = st.Page("pages/push_jobs.py", title="Push Jobs", icon="🚀")
timeline = st.Page("pages/timeline.py", title="Pipeline Timeline", icon="⏱️")

late_arrivals = st.Page("pages/late_arrivals.py", title="Late Arrivals", icon="⚠️")
poller = st.Page("pages/poller.py", title="ADLS Poller", icon="📡")
services = st.Page("pages/services.py", title="Services", icon="⚙️")

pg = st.navigation(
    {
        "Monitor": [dashboard, extracts, push_jobs, timeline],
        "Operations": [late_arrivals, poller, services],
    }
)

# ---------------------------------------------------------------------------
# Sidebar footer
# ---------------------------------------------------------------------------

with st.sidebar:
    st.divider()
    st.caption("INS Orchestrator Dashboard v0.1")

pg.run()
