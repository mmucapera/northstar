import streamlit as st


STATUS_COLORS = {
    # Extract statuses
    "NEW": "blue",
    "VALIDATED": "green",
    "PUSHED": "green",
    "VALIDATION_FAILED": "red",
    # Bronze
    "PENDING": "orange",
    "LOADED": "green",
    # B2S
    "NOT_STARTED": "gray",
    "RUNNING": "blue",
    "SUCCESS": "green",
    "FAILED": "red",
    "SKIPPED": "orange",
    # S2G
    "PROCESSING": "blue",
    # Push job
    "PARTIAL": "orange",
    "CANCELLED": "orange",
    "RECALLED": "orange",
}


def status_badge(status: str) -> str:
    """Return an HTML span styled as a colored badge for the given status."""
    color = STATUS_COLORS.get(status, "gray")
    return (
        f'<span style="background-color:{color};color:white;padding:2px 8px;'
        f'border-radius:10px;font-size:0.85em;font-weight:600;">{status}</span>'
    )


def render_metric_row(metrics: dict):
    """Render a row of st.metric cards from a {label: (value, delta)} dict.

    delta can be None.
    """
    cols = st.columns(len(metrics))
    for col, (label, (value, delta)) in zip(cols, metrics.items()):
        col.metric(label, value, delta)


def refresh_button(key: str = "refresh"):
    """A refresh button that triggers st.rerun when clicked."""
    if st.button("🔄 Refresh", key=key):
        st.rerun()
