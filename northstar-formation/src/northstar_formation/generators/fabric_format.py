"""Microsoft Fabric .Notebook format exporter.

This module converts notebook cell structures to the Fabric-native
.Notebook directory format, which consists of:
  - .platform: JSON metadata file
  - notebook-content.py: Python file with special comment markers

This format is required for deploying notebooks to Microsoft Fabric
via Git integration or API deployment.
"""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Any, Dict, List

from ..utils.logging import get_logger


if TYPE_CHECKING:
    from pathlib import Path

    from ..core.models import LakehouseConfig


logger = get_logger(__name__)


class FabricFormatExporter:
    """Export notebooks to Microsoft Fabric .Notebook directory format.

    The Fabric .Notebook format is a directory containing:
    - .platform: JSON file with notebook metadata
    - notebook-content.py: Python source with special comment markers

    Cell format in notebook-content.py:
    ```
    # CELL ********************
    code here

    # METADATA ********************
    # META {"language": "python", "language_group": "synapse_pyspark"}
    ```

    For SQL cells:
    ```
    # CELL ********************
    # MAGIC %%sql
    # MAGIC SELECT * FROM table

    # METADATA ********************
    # META {"language": "sparksql", "language_group": "synapse_pyspark"}
    ```
    """

    def __init__(self, default_lakehouse: LakehouseConfig | None = None) -> None:
        """Initialize the Fabric format exporter.

        Args:
            default_lakehouse: Optional default lakehouse configuration.
        """
        self.default_lakehouse = default_lakehouse

    def _apply_layer_prefix(self, model_name: str, layer: str = "") -> str:
        """Apply output naming rules based on layer.

        Rules:
          - bronze -> brz_<name> (unless already brz_)
          - silver -> slv_<name> (unless already slv_)

        """
        name = (model_name or "").strip()
        layer_norm = (layer or "").strip().lower()

        if not name:
            return model_name

        if layer_norm == "bronze":
            return name if name.lower().startswith("brz_") else f"brz_{name}"

        if layer_norm == "silver":
            return name if name.lower().startswith("slv_") else f"slv_{name}"

        return name

    def export(
        self,
        model_name: str,
        cells: List[Dict[str, Any]],
        output_dir: Path,
        lakehouse_config: LakehouseConfig | None = None,
        description: str = "",
        customer: str = "",
        layer: str = "",
    ) -> Path:
        """Export cells to Fabric .Notebook format.

        Args:
            model_name: Name of the model/notebook.
            cells: List of cell dictionaries (ipynb format).
            output_dir: Output directory path.
            lakehouse_config: Optional lakehouse configuration.
            description: Optional notebook description.
            customer: Customer name for deterministic logicalId generation.
            layer: Data layer (bronze, silver, gold) for deterministic logicalId.

        Returns:
            Path to the created .Notebook directory.
        """
        export_name = self._apply_layer_prefix(model_name, layer)

        # Create notebook directory
        notebook_dir = output_dir / f"{export_name}.Notebook"
        notebook_dir.mkdir(parents=True, exist_ok=True)

        # Get lakehouse config
        lakehouse = lakehouse_config or self.default_lakehouse

        # Write .platform file
        platform_content = self._build_platform_file(
            model_name=export_name,
            description=description,
            customer=customer,
            layer=layer,
        )
        platform_path = notebook_dir / ".platform"
        platform_path.write_text(json.dumps(platform_content, indent=2), encoding="utf-8")

        # Write notebook-content.py
        notebook_content = self._build_notebook_content(cells, lakehouse)
        content_path = notebook_dir / "notebook-content.py"
        content_path.write_text(notebook_content, encoding="utf-8")

        logger.info(f"Exported Fabric notebook: {notebook_dir}")
        return notebook_dir

    def export_all(
        self,
        notebooks: Dict[str, Dict[str, Any]],
        output_dir: Path,
        lakehouse_config: LakehouseConfig | None = None,
    ) -> Dict[str, Path]:
        """Export multiple notebooks to Fabric format.

        Args:
            notebooks: Dictionary of model_name -> notebook dict (ipynb format).
            output_dir: Output directory path.
            lakehouse_config: Optional lakehouse configuration.

        Returns:
            Dictionary of model_name -> notebook directory path.
        """
        results: Dict[str, Path] = {}

        for model_name, notebook in notebooks.items():
            cells = notebook.get("cells", [])
            try:
                path = self.export(
                    model_name=model_name,
                    cells=cells,
                    output_dir=output_dir,
                    lakehouse_config=lakehouse_config,
                )
                results[model_name] = path
            except Exception as e:
                logger.error(f"Failed to export {model_name}: {e}")

        return results

    def _generate_logical_id(self, customer: str, model_name: str, layer: str = "") -> str:
        """Generate a deterministic logicalId from customer, layer, and model name.

        Uses UUID5 with a fixed namespace to ensure the same customer+layer+model
        always produces the same logicalId. This is important for Fabric
        to recognize notebooks across regenerations.

        Args:
            customer: Customer name (e.g., "customer0").
            model_name: Model/notebook name (e.g., "d_fct_customer").
            layer: Data layer (e.g., "bronze", "silver", "gold").

        Returns:
            Deterministic UUID string.
        """
        # Use a fixed namespace for northstar-formation notebooks
        namespace = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # UUID namespace DNS

        # Combine customer, layer, and model for unique but deterministic ID
        # Layer is important because bronze.fct_customer != silver.fct_customer
        layer_part = f".{layer}" if layer else ""
        identifier = f"northstar-formation.{customer}{layer_part}.{model_name}".lower()

        return str(uuid.uuid5(namespace, identifier))

    def _build_platform_file(
        self,
        model_name: str,
        description: str = "",
        customer: str = "",
        layer: str = "",
    ) -> Dict[str, Any]:
        """Build the .platform JSON content.

        Args:
            model_name: Name of the notebook.
            description: Optional description.
            customer: Customer name for deterministic logicalId.
            layer: Data layer (bronze, silver, gold) for deterministic logicalId.

        Returns:
            Dictionary for .platform JSON file.
        """
        # Generate deterministic logicalId from customer + layer + model
        logical_id = self._generate_logical_id(customer or "default", model_name, layer)

        return {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {
                "type": "Notebook",
                "displayName": model_name,
                "description": description or f"Generated notebook for {model_name}",
            },
            "config": {
                "version": "2.0",
                "logicalId": logical_id,
            },
        }

    def _build_notebook_content(
        self,
        cells: List[Dict[str, Any]],
        lakehouse: LakehouseConfig | None = None,
    ) -> str:
        """Build the notebook-content.py file content.

        Args:
            cells: List of cell dictionaries.
            lakehouse: Optional lakehouse configuration.

        Returns:
            String content for notebook-content.py.
        """
        lines: List[str] = []

        # Header
        lines.append("# Fabric notebook source")
        lines.append("")

        # Notebook-level metadata with lakehouse dependencies
        lines.append("# METADATA ********************")
        lines.append("")

        metadata = self._build_notebook_metadata(lakehouse)
        for line in self._format_meta_block(metadata):
            lines.append(line)
        lines.append("")

        # Process each cell
        for cell in cells:
            cell_lines = self._convert_cell(cell)
            lines.extend(cell_lines)
            lines.append("")

        return "\n".join(lines)

    def _build_notebook_metadata(
        self,
        lakehouse: LakehouseConfig | None = None,
    ) -> Dict[str, Any]:
        """Build notebook-level metadata.

        Args:
            lakehouse: Optional lakehouse configuration.

        Returns:
            Metadata dictionary.
        """
        metadata: Dict[str, Any] = {
            "kernel_info": {
                "name": "synapse_pyspark",
            },
            "dependencies": {},
        }

        if lakehouse and lakehouse.is_configured():
            metadata["dependencies"]["lakehouse"] = {
                "default_lakehouse": lakehouse.id,
                "default_lakehouse_name": lakehouse.name,
                "default_lakehouse_workspace_id": lakehouse.workspace_id,
                "known_lakehouses": [{"id": lakehouse.id}],
            }

        return metadata

    def _format_meta_block(self, data: Dict[str, Any]) -> List[str]:
        """Format a metadata block with # META prefix.

        Produces output matching Fabric's expected format:
        ```
        # META {
        # META   "key": {
        # META     "nested": "value"
        # META   }
        # META }
        ```

        Args:
            data: Dictionary to format as JSON.

        Returns:
            List of lines with # META prefix.
        """
        lines: List[str] = []
        json_str = json.dumps(data, indent=2)

        # Split and prefix each line, preserving indentation
        for line in json_str.split("\n"):
            lines.append(f"# META {line}")

        return lines

    def _format_cell_metadata(self, language: str = "python") -> List[str]:
        """Format cell-level metadata block.

        Args:
            language: Cell language (python or sparksql).

        Returns:
            List of metadata lines.
        """
        metadata = {
            "language": language,
            "language_group": "synapse_pyspark",
        }
        lines = ["", "# METADATA ********************", ""]
        lines.extend(self._format_meta_block(metadata))
        return lines

    def _convert_cell(self, cell: Dict[str, Any]) -> List[str]:
        """Convert a single cell to Fabric format.

        Args:
            cell: Cell dictionary in ipynb format.

        Returns:
            List of lines for this cell.
        """
        cell_type = cell.get("cell_type", "code")
        source = cell.get("source", [])

        # Normalize source to string
        if isinstance(source, list):
            source_str = "".join(source)
        else:
            source_str = str(source)

        lines: List[str] = []

        # Cell marker
        lines.append("# CELL ********************")
        lines.append("")

        if cell_type == "markdown":
            # Markdown cells - prefix each line with # MARKDOWN
            for line in source_str.split("\n"):
                lines.append(f"# {line}")

            # Cell metadata
            lines.extend(self._format_cell_metadata("python"))

        elif cell_type == "code":
            # Check if this is SQL magic or configure magic
            source_stripped = source_str.strip()

            if source_stripped.startswith("%%sql") or source_stripped.startswith("# MAGIC %%sql"):
                # SQL cell
                lines.extend(self._convert_sql_cell(source_str))
            elif source_stripped.startswith("%%configure") or source_stripped.startswith("# MAGIC %%configure"):
                # Configure cell - wrap with # MAGIC prefix like Fabric does
                lines.extend(self._convert_configure_cell(source_str))
            else:
                # Regular Python cell
                lines.extend(self._convert_python_cell(source_str))

        return lines

    def _convert_python_cell(self, source: str) -> List[str]:
        """Convert a Python code cell.

        Args:
            source: Python source code.

        Returns:
            List of lines.
        """
        lines: List[str] = []

        # Add the code directly
        for line in source.rstrip("\n").split("\n"):
            lines.append(line)

        # Cell metadata
        lines.extend(self._format_cell_metadata("python"))

        return lines

    def _convert_sql_cell(self, source: str) -> List[str]:
        """Convert a SQL magic cell.

        Args:
            source: SQL source with %%sql magic.

        Returns:
            List of lines with # MAGIC prefix.
        """
        lines: List[str] = []

        # Remove existing %%sql if present and add as MAGIC
        source_clean = source.strip()
        if source_clean.startswith("%%sql"):
            source_clean = source_clean[5:].strip()
        elif source_clean.startswith("# MAGIC %%sql"):
            # Already in magic format, extract SQL
            sql_lines = []
            for line in source_clean.split("\n"):
                if line.startswith("# MAGIC "):
                    sql_lines.append(line[8:])
                elif line.strip() == "# MAGIC":
                    sql_lines.append("")
            source_clean = "\n".join(sql_lines).strip()
            if source_clean.startswith("%%sql"):
                source_clean = source_clean[5:].strip()

        # Add SQL with MAGIC prefix
        lines.append("# MAGIC %%sql")
        for line in source_clean.split("\n"):
            if line.strip():
                lines.append(f"# MAGIC {line}")
            else:
                lines.append("# MAGIC")

        # Cell metadata for SQL
        lines.extend(self._format_cell_metadata("sparksql"))

        return lines

    def _convert_configure_cell(self, source: str) -> List[str]:
        """Convert a %%configure magic cell.

        Fabric wraps %%configure cells with # MAGIC prefix,
        similar to %%sql cells but using python language metadata.

        Args:
            source: Configure source with %%configure magic.

        Returns:
            List of lines with # MAGIC prefix.
        """
        lines: List[str] = []

        # Normalize: strip existing # MAGIC prefixes if already present
        source_clean = source.strip()
        if source_clean.startswith("# MAGIC"):
            raw_lines = []
            for line in source_clean.split("\n"):
                if line.startswith("# MAGIC "):
                    raw_lines.append(line[8:])
                elif line.strip() == "# MAGIC":
                    raw_lines.append("")
                else:
                    raw_lines.append(line)
            source_clean = "\n".join(raw_lines).strip()

        # Re-emit every line with # MAGIC prefix
        for line in source_clean.split("\n"):
            if line.strip():
                lines.append(f"# MAGIC {line}")
            else:
                lines.append("# MAGIC")

        # Configure cells use python language metadata in Fabric
        lines.extend(self._format_cell_metadata("python"))

        return lines


def convert_ipynb_to_fabric(
    notebook: Dict[str, Any],
    model_name: str,
    output_dir: Path,
    lakehouse_config: LakehouseConfig | None = None,
) -> Path:
    """Convenience function to convert a single ipynb notebook to Fabric format.

    Args:
        notebook: Notebook dictionary in ipynb format.
        model_name: Name for the notebook.
        output_dir: Output directory.
        lakehouse_config: Optional lakehouse configuration.

    Returns:
        Path to the created .Notebook directory.
    """
    exporter = FabricFormatExporter()
    return exporter.export(
        model_name=model_name,
        cells=notebook.get("cells", []),
        output_dir=output_dir,
        lakehouse_config=lakehouse_config,
    )