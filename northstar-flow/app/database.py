import struct
from itertools import chain, repeat
import pyodbc
from azure.identity import ClientSecretCredential
from typing import Optional, Any, List, Dict
import logging
from app.config import settings

logger = logging.getLogger(__name__)


class OrchestratorDBConnection:
    """Manages connection to the INS Orchestrator pipeline database (Fabric SQL endpoint)."""

    def __init__(self):
        self.connection: Optional[pyodbc.Connection] = None

    def _get_connection(self) -> pyodbc.Connection:
        endpoint = settings.ins_orch_sql_endpoint
        database = settings.ins_orch_database
        tenant_id = settings.azure_tenant_id
        client_id = settings.azure_client_id

        logger.info(
            f"Opening Orchestrator DB connection | server={endpoint} | "
            f"database={database} | tenant={tenant_id} | client_id={client_id}"
        )

        try:
            logger.info("Acquiring Entra token for scope https://database.windows.net//.default")
            credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=settings.azure_client_secret,
            )
            token = credential.get_token("https://database.windows.net//.default")
            logger.info(f"Token acquired (expires_on={token.expires_on})")

            token_as_bytes = bytes(token.token, "UTF-8")
            encoded_bytes = bytes(chain.from_iterable(zip(token_as_bytes, repeat(0))))
            token_struct = struct.pack("<i", len(encoded_bytes)) + encoded_bytes

            conn_str = (
                f"Driver={{ODBC Driver 18 for SQL Server}};"
                f"Server={endpoint};"
                f"Database={database};"
                f"Encrypt=yes;"
                f"TrustServerCertificate=no;"
                f"Connection Timeout=30;"
            )
            logger.info(f"Calling pyodbc.connect | server={endpoint} | database={database}")

            conn = pyodbc.connect(conn_str, attrs_before={1256: token_struct})

            try:
                cursor = conn.cursor()
                cursor.execute("SELECT SUSER_SNAME(), DB_NAME(), @@SERVERNAME")
                row = cursor.fetchone()
                cursor.close()
                logger.info(
                    f"DB connection established | identity={row[0]} | db={row[1]} | server={row[2]}"
                )
            except Exception as identity_err:
                logger.warning(f"Connected but identity probe failed: {identity_err}")

            return conn

        except Exception as e:
            logger.error(
                f"Failed to connect to Orchestrator DB | server={endpoint} | "
                f"database={database} | tenant={tenant_id} | client_id={client_id} | error={e}"
            )
            raise

    def get_connection(self) -> pyodbc.Connection:
        if not self.connection or not self._is_connection_alive():
            self.connection = self._get_connection()
        return self.connection

    def _is_connection_alive(self) -> bool:
        if not self.connection:
            return False
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            return True
        except Exception:
            return False

    def execute_query(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            columns = [col[0] for col in cursor.description] if cursor.description else []
            results = []
            if columns:
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))

            # Commit for write operations (INSERT/UPDATE/DELETE)
            if not columns:
                conn.commit()

            cursor.close()
            return results

        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            logger.error(f"Query: {query}")
            raise

    def execute_single(self, query: str, params: Optional[tuple] = None) -> Optional[Dict[str, Any]]:
        results = self.execute_query(query, params)
        return results[0] if results else None

    def call_sp(
        self,
        sp_name: str,
        params: Dict[str, Any],
        output_params: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Call a stored procedure with named parameters and optional OUTPUT params.

        Uses DECLARE/EXEC/SELECT pattern because pyodbc does not support
        OUTPUT parameter binding directly.

        Returns a dict with:
          - 'output': dict of output param name -> value
          - 'result': first result set as List[Dict] (if any)
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            output_param_names = output_params or []

            # Build DECLARE statements for output params
            declare_parts = []
            for name in output_param_names:
                declare_parts.append(f"DECLARE @{name} INT;")

            # Build EXEC parameter list
            param_parts = []
            param_values = []

            for name, value in params.items():
                if name in output_param_names:
                    # Skip — output params are declared as variables, not passed as ?
                    continue
                param_parts.append(f"@{name} = ?")
                param_values.append(value)

            # Append output params as variable references
            for name in output_param_names:
                param_parts.append(f"@{name} = @{name} OUTPUT")

            # Build SELECT to retrieve output param values
            select_parts = []
            for name in output_param_names:
                select_parts.append(f"@{name} AS [{name}]")

            sql_lines = []
            sql_lines.extend(declare_parts)
            sql_lines.append(f"EXEC [dbo].[{sp_name}] {', '.join(param_parts)};")
            if select_parts:
                sql_lines.append(f"SELECT {', '.join(select_parts)};")

            sql = "\n".join(sql_lines)
            cursor.execute(sql, param_values)

            # Capture first result set (from SP itself, if any)
            result_set = []
            if cursor.description:
                columns = [col[0] for col in cursor.description]
                for row in cursor.fetchall():
                    result_set.append(dict(zip(columns, row)))

            # Capture output param values from the SELECT statement
            output_values = {}
            if output_param_names:
                while cursor.nextset():
                    if cursor.description:
                        columns = [col[0] for col in cursor.description]
                        rows = cursor.fetchall()
                        if rows:
                            output_values = dict(zip(columns, rows[0]))
                        break

            conn.commit()
            cursor.close()

            return {"output": output_values, "result": result_set}

        except Exception as e:
            logger.error(f"Stored procedure [{sp_name}] failed: {e}")
            raise

    def close(self):
        if self.connection:
            self.connection.close()
            self.connection = None


# Singleton — only instantiated if config is set
db: Optional[OrchestratorDBConnection] = None
if settings.ins_orch_sql_endpoint and settings.ins_orch_database:
    logger.info(
        f"Orchestrator DB configured | server={settings.ins_orch_sql_endpoint} | "
        f"database={settings.ins_orch_database} | tenant={settings.azure_tenant_id} | "
        f"client_id={settings.azure_client_id} (connection deferred until first use)"
    )
    db = OrchestratorDBConnection()
else:
    logger.warning(
        "Orchestrator DB NOT configured — INS_ORCH_SQL_ENDPOINT or INS_ORCH_DATABASE missing. "
        f"endpoint_set={bool(settings.ins_orch_sql_endpoint)} | "
        f"database_set={bool(settings.ins_orch_database)}"
    )
