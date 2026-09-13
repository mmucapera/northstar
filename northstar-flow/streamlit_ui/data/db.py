import struct
import os
from itertools import chain, repeat
from pathlib import Path
from typing import Optional, Any, List, Dict

import pyodbc
import streamlit as st
from azure.identity import ClientSecretCredential
from dotenv import load_dotenv

# Load .env from streamlit_ui root
_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.exists():
    load_dotenv(_env_file)


def _get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """Read from st.secrets first, fall back to env var."""
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)


def _check_db_config() -> Optional[str]:
    """Return an error message if required DB config is missing, else None."""
    required = {
        "AZURE_TENANT_ID": _get_env("AZURE_TENANT_ID"),
        "AZURE_CLIENT_ID": _get_env("AZURE_CLIENT_ID"),
        "AZURE_CLIENT_SECRET": _get_env("AZURE_CLIENT_SECRET"),
        "INS_ORCH_SQL_ENDPOINT": _get_env("INS_ORCH_SQL_ENDPOINT"),
        "INS_ORCH_DATABASE": _get_env("INS_ORCH_DATABASE"),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        return f"Missing DB configuration: {', '.join(missing)}. Set them in .env or Streamlit secrets."
    return None


class DBReader:
    """Read-only connection to the Orchestrator pipeline database (Fabric SQL)."""

    def __init__(self):
        self._conn: Optional[pyodbc.Connection] = None
        self._config_error: Optional[str] = _check_db_config()

    def _connect(self) -> pyodbc.Connection:
        if self._config_error:
            raise RuntimeError(self._config_error)

        credential = ClientSecretCredential(
            tenant_id=_get_env("AZURE_TENANT_ID", ""),
            client_id=_get_env("AZURE_CLIENT_ID", ""),
            client_secret=_get_env("AZURE_CLIENT_SECRET", ""),
        )
        token = credential.get_token("https://database.windows.net//.default")

        token_bytes = bytes(token.token, "UTF-8")
        encoded = bytes(chain.from_iterable(zip(token_bytes, repeat(0))))
        token_struct = struct.pack("<i", len(encoded)) + encoded

        conn_str = (
            f"Driver={{ODBC Driver 18 for SQL Server}};"
            f"Server={_get_env('INS_ORCH_SQL_ENDPOINT', '')};"
            f"Database={_get_env('INS_ORCH_DATABASE', '')};"
            f"Encrypt=yes;"
            f"TrustServerCertificate=no;"
            f"Connection Timeout=30;"
        )
        return pyodbc.connect(conn_str, attrs_before={1256: token_struct})

    @property
    def conn(self) -> pyodbc.Connection:
        if self._conn is None or not self._alive():
            self._conn = self._connect()
        return self._conn

    def _alive(self) -> bool:
        if not self._conn:
            return False
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
            return True
        except Exception:
            return False

    def query(self, sql: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        try:
            cur.execute(sql, params or ())
            if not cur.description:
                return []
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            cur.close()

    def query_single(self, sql: str, params: Optional[tuple] = None) -> Optional[Dict[str, Any]]:
        rows = self.query(sql, params)
        return rows[0] if rows else None


@st.cache_resource
def get_db() -> DBReader:
    """Cached singleton — one DB connection per Streamlit session."""
    return DBReader()


def require_db() -> DBReader:
    """Get DB reader, or stop the page with an error if not configured."""
    db = get_db()
    if db._config_error:
        st.error(db._config_error)
        st.stop()
    return db
