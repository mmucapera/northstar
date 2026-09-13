import streamlit as st
import pandas as pd

from data import api_client
from components.helpers import refresh_button

st.header("ADLS Poller")
refresh_button()

# ---------------------------------------------------------------------------
# Load sources
# ---------------------------------------------------------------------------

try:
    sources = api_client.get_poller_sources()
except Exception:
    sources = []

# ---------------------------------------------------------------------------
# Aggregate status
# ---------------------------------------------------------------------------

try:
    status = api_client.get_poller_status()
except Exception as exc:
    st.error(f"Could not reach Orchestrator API: {exc}")
    st.stop()

is_running = status.get("is_running", False)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Status", "Running" if is_running else "Stopped")
col2.metric("Poll Cycles", status.get("poll_cycles", 0))
col3.metric("New Files Detected", status.get("new_files_detected", 0))
col4.metric("Errors", status.get("errors", 0))

extras = st.columns(3)
extras[0].metric("Elapsed (s)", f"{status.get('elapsed_seconds', 0):.0f}")
extras[1].caption(f"Started: {status.get('started_at', '—')}")
extras[2].caption(f"Last poll: {status.get('last_poll_at', '—')}")

# ---------------------------------------------------------------------------
# Controls (aggregate)
# ---------------------------------------------------------------------------

st.subheader("Controls")
btn_col1, btn_col2, _ = st.columns([1, 1, 4])

with btn_col1:
    if st.button("▶ Start All", disabled=is_running, key="poller_start"):
        try:
            api_client.start_poller()
            st.success("Poller(s) started.")
            st.rerun()
        except Exception as exc:
            st.error(f"Failed: {exc}")

with btn_col2:
    if st.button("⏹ Stop All", disabled=not is_running, key="poller_stop"):
        try:
            api_client.stop_poller()
            st.success("Poller(s) stopped.")
            st.rerun()
        except Exception as exc:
            st.error(f"Failed: {exc}")

# ---------------------------------------------------------------------------
# Per-source details (only shown when multiple sources exist)
# ---------------------------------------------------------------------------

if len(sources) > 1:
    st.subheader("Sources")

    source_labels = {s["source_id"]: f'{s["source_id"]} — {s.get("label", "")}' for s in sources}
    selected_source = st.selectbox(
        "Select source",
        options=list(source_labels.keys()),
        format_func=lambda x: source_labels[x],
        key="poller_source_select",
    )

    if selected_source:
        try:
            src_status = api_client.get_poller_source_status(selected_source)
        except Exception as exc:
            st.error(f"Could not fetch source status: {exc}")
            src_status = {}

        src_running = src_status.get("is_running", False)

        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("Status", "Running" if src_running else "Stopped")
        sc2.metric("Poll Cycles", src_status.get("poll_cycles", 0))
        sc3.metric("Files Detected", src_status.get("new_files_detected", 0))
        sc4.metric("Errors", src_status.get("errors", 0))

        sb1, sb2, _ = st.columns([1, 1, 4])
        with sb1:
            if st.button("▶ Start", disabled=src_running, key=f"src_start_{selected_source}"):
                try:
                    api_client.start_poller_source(selected_source)
                    st.success(f"Source '{selected_source}' started.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Failed: {exc}")
        with sb2:
            if st.button("⏹ Stop", disabled=not src_running, key=f"src_stop_{selected_source}"):
                try:
                    api_client.stop_poller_source(selected_source)
                    st.success(f"Source '{selected_source}' stopped.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Failed: {exc}")

# ---------------------------------------------------------------------------
# Manage Sources (DB-backed CRUD)
# ---------------------------------------------------------------------------

st.subheader("Manage Sources")

# --- Current sources table ---
if sources:
    src_df = pd.DataFrame(sources)
    display_cols = ["source_id", "label", "storage_account", "container",
                    "folder_path", "poll_interval_seconds", "enabled", "is_running"]
    src_df = src_df[[c for c in display_cols if c in src_df.columns]]
    st.dataframe(src_df, width="stretch", hide_index=True)
else:
    st.info("No ADLS sources configured.")

# --- Add source ---
with st.expander("Add New Source"):
    with st.form("add_source_form"):
        new_id = st.text_input("Source ID", placeholder="e.g. client-raw-data", max_chars=50)
        new_label = st.text_input("Label", placeholder="e.g. Client Raw Data Feed")
        new_account = st.text_input("Storage Account", placeholder="mystorageaccount")
        new_container = st.text_input("Container", placeholder="raw-data")
        new_folder = st.text_input("Folder Path", placeholder="incoming/", value="")
        new_sas = st.text_input("SAS Token (env var ref)", placeholder="${MY_SAS_TOKEN}",
                                help="Use ${ENV_VAR_NAME} to reference a container environment variable.")
        new_interval = st.number_input("Poll Interval (seconds)", min_value=5, value=10)
        new_enabled = st.checkbox("Enabled", value=True)
        submitted = st.form_submit_button("Add Source")

        if submitted:
            if not all([new_id, new_account, new_container, new_sas]):
                st.error("Source ID, Storage Account, Container, and SAS Token are required.")
            else:
                try:
                    api_client.create_poller_source({
                        "source_id": new_id,
                        "label": new_label,
                        "storage_account": new_account,
                        "container": new_container,
                        "folder_path": new_folder,
                        "sas_token": new_sas,
                        "poll_interval_seconds": new_interval,
                        "enabled": new_enabled,
                    })
                    st.success(f"Source '{new_id}' created.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Failed to create source: {exc}")

# --- Edit / Delete existing source ---
if sources:
    with st.expander("Edit / Delete Source"):
        edit_source_id = st.selectbox(
            "Select source to edit",
            options=[s["source_id"] for s in sources],
            key="edit_source_select",
        )
        selected_src = next((s for s in sources if s["source_id"] == edit_source_id), None)

        if selected_src:
            tab_edit, tab_delete = st.tabs(["Edit", "Delete"])

            with tab_edit:
                with st.form("edit_source_form"):
                    ed_label = st.text_input("Label", value=selected_src.get("label", ""))
                    ed_account = st.text_input("Storage Account", value=selected_src.get("storage_account", ""))
                    ed_container = st.text_input("Container", value=selected_src.get("container", ""))
                    ed_folder = st.text_input("Folder Path", value=selected_src.get("folder_path", ""))
                    ed_sas = st.text_input("SAS Token (env var ref)", value="",
                                           help="Leave blank to keep current. Use ${ENV_VAR_NAME}.")
                    ed_interval = st.number_input("Poll Interval (seconds)", min_value=5,
                                                  value=selected_src.get("poll_interval_seconds", 10))
                    ed_enabled = st.checkbox("Enabled", value=selected_src.get("enabled", True))
                    edit_submitted = st.form_submit_button("Save Changes")

                    if edit_submitted:
                        updates = {}
                        if ed_label != selected_src.get("label", ""):
                            updates["label"] = ed_label
                        if ed_account != selected_src.get("storage_account", ""):
                            updates["storage_account"] = ed_account
                        if ed_container != selected_src.get("container", ""):
                            updates["container"] = ed_container
                        if ed_folder != selected_src.get("folder_path", ""):
                            updates["folder_path"] = ed_folder
                        if ed_sas:
                            updates["sas_token"] = ed_sas
                        if ed_interval != selected_src.get("poll_interval_seconds", 10):
                            updates["poll_interval_seconds"] = ed_interval
                        if ed_enabled != selected_src.get("enabled", True):
                            updates["enabled"] = ed_enabled

                        if not updates:
                            st.warning("No changes detected.")
                        else:
                            try:
                                api_client.update_poller_source(edit_source_id, updates)
                                st.success(f"Source '{edit_source_id}' updated. Poller restarted.")
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Failed to update source: {exc}")

            with tab_delete:
                st.warning(f"This will stop the poller and permanently remove source **{edit_source_id}**.")
                if st.button("Delete Source", type="primary", key="delete_source_btn"):
                    try:
                        api_client.delete_poller_source(edit_source_id)
                        st.success(f"Source '{edit_source_id}' deleted.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Failed to delete source: {exc}")

# ---------------------------------------------------------------------------
# Detected files
# ---------------------------------------------------------------------------

st.subheader("Detected Files")

filter_cols = st.columns(2)
with filter_cols[0]:
    filter_status = st.selectbox("Filter by status", ["All", "REGISTERED", "FAILED"], key="poller_file_status")
with filter_cols[1]:
    if len(sources) > 1:
        source_options = ["All Sources"] + [s["source_id"] for s in sources]
        filter_source = st.selectbox("Filter by source", source_options, key="poller_file_source")
    else:
        filter_source = "All Sources"

try:
    files = api_client.get_poller_files(
        status=None if filter_status == "All" else filter_status,
        limit=100,
        source_id=None if filter_source == "All Sources" else filter_source,
    )
except Exception as exc:
    st.error(f"Could not fetch files: {exc}")
    files = []

if files:
    df = pd.DataFrame(files)
    column_config = {
        "file_name": "File Name",
        "detected_at": st.column_config.DatetimeColumn("Detected At", format="YYYY-MM-DD HH:mm"),
        "status": "Status",
        "extract_id": st.column_config.NumberColumn("Extract ID"),
        "error_message": "Error",
    }
    if len(sources) > 1:
        column_config["source_id"] = "Source"
    else:
        # Hide source_id column when single source
        df = df.drop(columns=["source_id"], errors="ignore")

    st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        column_config=column_config,
    )
else:
    st.info("No files detected yet.")
