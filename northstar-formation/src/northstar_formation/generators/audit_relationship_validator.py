"""Semantic model TMDL relationship validator - generates validation notebooks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from ..utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RelationshipKey:
    """Represents a key in a relationship."""
    column: str
    table: str


@dataclass
class Relationship:
    """Represents a relationship between two tables."""
    name: str
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    semantic_model: str = ""  # Track which semantic model this came from
    join_type: str = "inner"


@dataclass
class TableDefinition:
    """Represents a table/entity in a semantic model."""
    name: str
    table_name: Optional[str] = None
    columns: Dict[str, str] = field(default_factory=dict)  # column_name -> data_type
    is_dimension: bool = False
    is_fact: bool = False


class TMDLParser:
    """Parser for Microsoft Fabric TMDL (Tabular Model Definition Language) files."""

    def __init__(self):
        self.tables: Dict[str, TableDefinition] = {}
        self.relationships: List[Relationship] = []
        self._current_semantic_model: str = ""

    def parse_file(self, file_path: Path) -> None:
        """Parse a single TMDL file (text format)."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse relationships from relationships.tmdl
            if file_path.name == "relationships.tmdl":
                self._parse_relationships_tmdl(content)
            # Parse table definitions from individual table files
            elif file_path.name.endswith(".tmdl") and file_path.parent.name == "tables":
                self._parse_table_tmdl(content, file_path.name)
                    
            if file_path.name == "relationships.tmdl":
                logger.debug(f"Parsed {file_path.name}: {len(self.relationships)} relationships")
            elif file_path.parent.name == "tables":
                logger.debug(f"Parsed {file_path.name}: table definition")
        except Exception as e:
            logger.error(f"Error parsing {file_path}: {e}")

    def parse_directory(self, directory: Path) -> Tuple[Dict[str, TableDefinition], List[Relationship]]:
        """Recursively parse all TMDL files in a directory."""
        self.tables.clear()
        self.relationships.clear()
        
        tmdl_files = list(directory.rglob("*.tmdl"))
        
        if not tmdl_files:
            logger.warning(f"No .tmdl files found in {directory}")
            return self.tables, self.relationships
        
        logger.info(f"Found {len(tmdl_files)} TMDL file(s) in {directory}")
        
        # First pass: parse all table definitions
        for tmdl_file in tmdl_files:
            if tmdl_file.parent.name == "tables":
                self.parse_file(tmdl_file)
        
        # Second pass: parse relationships
        for tmdl_file in tmdl_files:
            if tmdl_file.name == "relationships.tmdl":
                self.parse_file(tmdl_file)
        
        logger.info(f"Loaded {len(self.tables)} tables and {len(self.relationships)} relationships")
        
        return self.tables, self.relationships

    def parse_semantic_models_directory(self, parent_directory: Path) -> Tuple[Dict[str, TableDefinition], List[Relationship]]:
        """Parse all semantic models in a parent directory.
        
        This method finds all *.SemanticModel directories and processes all relationships,
        combining them into a single set of validations.
        
        Args:
            parent_directory: Path containing multiple *.SemanticModel directories
            
        Returns:
            Tuple of (tables_dict, relationships_list) from all semantic models
        """
        self.tables.clear()
        self.relationships.clear()
        
        # Find all .SemanticModel directories
        semantic_model_dirs = [
            d for d in parent_directory.iterdir() 
            if d.is_dir() and d.name.endswith('.SemanticModel')
        ]
        
        if not semantic_model_dirs:
            logger.warning(f"No .SemanticModel directories found in {parent_directory}")
            return self.tables, self.relationships
        
        logger.info(f"Found {len(semantic_model_dirs)} semantic model(s)")
        
        # Process each semantic model
        for sm_dir in sorted(semantic_model_dirs):
            sm_name = sm_dir.name.replace('.SemanticModel', '')
            definition_dir = sm_dir / 'definition'
            
            if not definition_dir.exists():
                logger.warning(f"No definition directory in {sm_dir}")
                continue
            
            logger.info(f"Processing semantic model: {sm_name}")
            
            tmdl_files = list(definition_dir.rglob("*.tmdl"))
            
            # Parse table definitions from this semantic model
            for tmdl_file in tmdl_files:
                if tmdl_file.parent.name == "tables":
                    self.parse_file(tmdl_file)
            
            # Parse relationships from this semantic model
            for tmdl_file in tmdl_files:
                if tmdl_file.name == "relationships.tmdl":
                    # Store semantic model name in context before parsing
                    self._current_semantic_model = sm_name
                    self.parse_file(tmdl_file)
                    self._current_semantic_model = ""
        
        logger.info(f"Loaded {len(self.tables)} total tables and {len(self.relationships)} total relationships from {len(semantic_model_dirs)} semantic models")
        
        return self.tables, self.relationships

    def _parse_table_tmdl(self, content: str, filename: str) -> None:
        """Parse a table definition from TMDL text format."""
        try:
            lines = content.split('\n')
            
            # First line should be: table <table_name>
            first_line = lines[0].strip() if lines else ""
            if not first_line.startswith("table "):
                return
            
            table_name = first_line.replace("table ", "").strip()
            if not table_name:
                return
            
            # Determine if it's a dimension or fact
            is_fact = (
                table_name.startswith('f_')
                or table_name.startswith('fct_')
                or table_name.startswith('fact_')
            )
            is_dimension = table_name.startswith('d_') or table_name.startswith('dim_')
            
            # Extract columns
            columns = {}
            current_indent = 0
            in_column = False
            current_column = None
            
            for i, line in enumerate(lines[1:], 1):
                if not line.strip():
                    continue
                
                # Check if this is a new column definition
                if line.startswith('\tcolumn '):
                    in_column = True
                    current_column = line.replace('\tcolumn ', '').strip()
                    columns[current_column] = 'unknown'
                # Check for dataType
                elif in_column and 'dataType:' in line and current_column:
                    # Extract data type
                    data_type = line.split('dataType:')[1].strip()
                    columns[current_column] = data_type
            
            table_def = TableDefinition(
                name=table_name,
                table_name=table_name,
                columns=columns,
                is_fact=is_fact,
                is_dimension=is_dimension
            )
            
            self.tables[table_name] = table_def
            logger.debug(f"Processed table: {table_name} (fact={is_fact}, dim={is_dimension}, cols={len(columns)})")
        except Exception as e:
            logger.error(f"Error processing table {filename}: {e}")

    def _parse_relationships_tmdl(self, content: str) -> None:
        """Parse relationships from relationships.tmdl text format."""
        try:
            lines = content.split('\n')
            
            current_rel_id = None
            current_from_column = None
            current_to_column = None
            
            for line in lines:
                line_stripped = line.strip()
                
                # New relationship
                if line_stripped.startswith("relationship "):
                    # Save previous relationship if exists
                    if current_rel_id and current_from_column and current_to_column:
                        self._create_relationship(
                            current_rel_id, current_from_column, current_to_column
                        )
                    
                    # Reset for new relationship
                    current_rel_id = line_stripped.replace("relationship ", "").strip()
                    current_from_column = None
                    current_to_column = None
                
                # Extract fromColumn - may or may not have table name prefix
                elif 'fromColumn:' in line_stripped and current_rel_id:
                    from_col_full = line_stripped.split('fromColumn:', 1)[1].strip()
                    current_from_column = from_col_full
                
                # Extract toColumn - may or may not have table name prefix
                elif 'toColumn:' in line_stripped and current_rel_id:
                    to_col_full = line_stripped.split('toColumn:', 1)[1].strip()
                    current_to_column = to_col_full
            
            # Don't forget the last relationship
            if current_rel_id and current_from_column and current_to_column:
                self._create_relationship(
                    current_rel_id, current_from_column, current_to_column
                )
                
        except Exception as e:
            logger.error(f"Error parsing relationships: {e}")

    def _create_relationship(self, rel_id: str, from_col_full: str, to_col_full: str) -> None:
        """Create a relationship from parsed columns in format 'table.column'."""
        try:
            # Remove quotes if present
            from_col_full = from_col_full.strip("'\"")
            to_col_full = to_col_full.strip("'\"")
            
            # Parse from_col_full format: "table.column"
            if '.' in from_col_full:
                from_parts = from_col_full.rsplit('.', 1)
                from_table = from_parts[0].strip().strip("'\"")
                from_column = from_parts[1].strip().strip("'\"")
            else:
                logger.debug(f"Invalid from column format: {from_col_full}")
                return
            
            # Parse to_col_full format: "table.column"
            if '.' in to_col_full:
                to_parts = to_col_full.rsplit('.', 1)
                to_table = to_parts[0].strip().strip("'\"")
                to_column = to_parts[1].strip().strip("'\"")
            else:
                logger.debug(f"Invalid to column format: {to_col_full}")
                return
            
            relationship = Relationship(
                name=rel_id[:8],  # Use first 8 chars of UUID for short name
                from_table=from_table,
                from_column=from_column,
                to_table=to_table,
                to_column=to_column,
                semantic_model=self._current_semantic_model
            )
            self.relationships.append(relationship)
            logger.debug(f"Processed relationship: {from_table}.{from_column} → {to_table}.{to_column}")
        except Exception as e:
            logger.error(f"Error creating relationship: {e}")


class ValidationNotebookGenerator:
    """Generates validation notebooks for semantic model relationships."""

    def __init__(self, tables: Dict[str, TableDefinition], relationships: List[Relationship], lakehouse_name: str = "lkh_customer0_schema_enabled"):
        self.tables = tables
        self.relationships = relationships
        self.lakehouse_name = lakehouse_name

    def generate_notebook(self) -> Dict[str, Any]:
        """Generate a complete validation notebook structure for Fabric."""
        cells = []

        # Fabric configuration and setup cells
        # cells.append(self._create_fabric_metadata_cell())
        cells.append(self._create_fabric_configure_cell())
        cells.append(self._create_fabric_logging_import_cell())
        cells.append(self._create_fabric_config_import_cell())
        cells.append(self._create_logging_setup_cell())
        cells.append(self._create_table_setup_cell())
        cells.append(self._create_schema_setup_cell())

        # Generate validation cells for each relationship
        fact_tables = {name: table for name, table in self.tables.items() if table.is_fact}
        
        if fact_tables:
            for fact_name, fact_table in fact_tables.items():
                # Find relationships for this fact table
                related_rels = [r for r in self.relationships if r.from_table == fact_name]
                
                if related_rels:
                    cells.append(self._create_markdown_cell(
                        f"## Validating {fact_name}"
                    ))

                    for rel in related_rels:
                        # Validate that dimension exists
                        if rel.to_table not in self.tables:
                            cells.append(self._create_python_code_cell(
                                f"# WARNING: Dimension '{rel.to_table}' referenced by '{rel.from_table}' does not exist\nlogger.warning('Missing dimension: {rel.to_table}')"
                            ))
                            continue

                        validation_cell = self._create_fabric_validation_cell(rel, fact_table)
                        cells.append(validation_cell)
        else:
            cells.append(self._create_markdown_cell(
                "## No Fact Tables Found\n\nNo tables starting with 'f_', 'fct_', or 'fact_' were found."
            ))


        return {
            "cells": cells,
            "metadata": {
                "language_info": {"name": "python"},
                "kernelspec": {"name": "python3", "display_name": "Python 3"}
            },
            "nbformat": 4,
            "nbformat_minor": 2
        }

    def _create_fabric_metadata_cell(self) -> Dict[str, Any]:
        """Create Fabric notebook metadata cell."""
        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": []
        }

    def _create_fabric_configure_cell(self) -> Dict[str, Any]:
        """Create Fabric %%configure cell."""
        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "%%configure\n",
                "{\n",
                f"    \"defaultLakehouse\": {{\n",
                f"        \"name\": \"{self.lakehouse_name}\"\n",
                "    }\n",
                "}\n"
            ]
        }

    def _create_fabric_logging_import_cell(self) -> Dict[str, Any]:
        """Create cell with fabric logging import."""
        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "%run nb_utils_logging\n"
            ]
        }

    def _create_fabric_config_import_cell(self) -> Dict[str, Any]:
        """Create cell with fabric config import."""
        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "%run nb_utils_config\n"
            ]
        }

    def _create_logging_setup_cell(self) -> Dict[str, Any]:
        """Create cell with logging initialization."""
        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "import logging\n",
                "from datetime import datetime\n",
                "from pyspark.sql.types import StructType, StructField, StringType, IntegerType, TimestampType, DoubleType, BooleanType\n",
                "import time\n",
                "import uuid\n",
                "\n",
                "# Setup logging\n",
                "logging.basicConfig(level=logging.INFO)\n",
                "logger = logging.getLogger('semantic_model_validator')\n",
                "\n",
                "validation_start_time = datetime.now()\n",
                "logger.info(f'Starting semantic model relationship validations at {validation_start_time}')\n"
            ]
        }

    def _create_table_setup_cell(self) -> Dict[str, Any]:
        """Create cell to setup validation results table."""
        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# Create validation results table if it doesn't exist\n",
                "logger.info('Setting up validation results table')\n",
                "\n",
                "spark.sql('''\n",
                "    CREATE TABLE IF NOT EXISTS log.audit_relationship_validator (\n",
                "        validation_id STRING,\n",
                "        validation_timestamp TIMESTAMP,\n",
                "        validation_date STRING,\n",
                "        relationship_name STRING,\n",
                "        fact_table STRING,\n",
                "        fact_column STRING,\n",
                "        dimension_table STRING,\n",
                "        dimension_column STRING,\n",
                "        orphaned_key_count INT,\n",
                "        sample_orphaned_keys STRING,\n",
                "        validation_passed BOOLEAN,\n",
                "        execution_time_ms DOUBLE,\n",
                "        error_message STRING\n",
                "    )\n",
                "    USING DELTA\n",
                "''')\n",
                "\n",
                "logger.info('Validation results table ready')\n"
            ]
        }

    def _create_schema_setup_cell(self) -> Dict[str, Any]:
        """Create cell to define the validation result schema once."""
        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "# Define result schema once for all validation cells\n",
                "result_schema = StructType([\n",
                "    StructField('validation_id', StringType()),\n",
                "    StructField('validation_timestamp', TimestampType()),\n",
                "    StructField('validation_date', StringType()),\n",
                "    StructField('relationship_name', StringType()),\n",
                "    StructField('fact_table', StringType()),\n",
                "    StructField('fact_column', StringType()),\n",
                "    StructField('dimension_table', StringType()),\n",
                "    StructField('dimension_column', StringType()),\n",
                "    StructField('orphaned_key_count', IntegerType()),\n",
                "    StructField('sample_orphaned_keys', StringType()),\n",
                "    StructField('validation_passed', BooleanType()),\n",
                "    StructField('execution_time_ms', DoubleType()),\n",
                "    StructField('error_message', StringType())\n",
                "])\n",
                "\n",
                "logger.info('Validation result schema defined')\n"
            ]
        }

    def _create_markdown_cell(self, content: str) -> Dict[str, Any]:
        """Create a markdown cell."""
        return {
            "cell_type": "markdown",
            "metadata": {},
            "source": content.split('\n')
        }

    def _create_python_code_cell(self, code: str) -> Dict[str, Any]:
        """Create a Python code cell with Fabric metadata."""
        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [code + "\n"]
        }

    def _create_fabric_validation_cell(self, rel: Relationship, fact_table: TableDefinition) -> Dict[str, Any]:
        """Create a validation cell that executes query and logs results."""
        sm_info = f" [{rel.semantic_model}]" if rel.semantic_model else ""
        code = (
            f"# Validate relationship"
            f" From: {rel.from_table}.{rel.from_column} -> To: {rel.to_table}.{rel.to_column}\n"
            f"\n"
            f"validation_id = str(uuid.uuid4())\n"
            f"_start_time = time.time()\n"
            f"error_msg = None\n"
            f"\n"
            f"try:\n"
            f"    logger.info(f'Validating: {rel.from_table}.{rel.from_column} -> {rel.to_table}.{rel.to_column}')\n"
            f"    \n"
            f"    # Query to find orphaned keys\n"
            f"    orphan_query = f'''\n"
            f"    SELECT\n"
            f"        DISTINCT {rel.from_column}\n"
            f"    FROM gold.{rel.from_table}\n"
            f"    WHERE {rel.from_column} IS NOT NULL\n"
            f"    AND {rel.from_column} NOT IN (\n"
            f"        SELECT {rel.to_column} FROM gold.{rel.to_table}\n"
            f"    )\n"
            f"    LIMIT 100\n"
            f"    '''\n"
            f"    \n"
            f"    # Execute query\n"
            f"    orphan_df = spark.sql(orphan_query)\n"
            f"    orphan_count = orphan_df.count()\n"
            f"    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''\n"
            f"    \n"
            f"    _elapsed = (time.time() - _start_time) * 1000\n"
            f"    validation_passed = orphan_count == 0\n"
            f"    \n"
            f"    logger.info(f'Result: {{orphan_count}} orphaned keys found, passed={{validation_passed}}')\n"
            f"    \n"
            f"    # Create result row\n"
            f"    _now = datetime.now()\n"
            f"    result_data = [\n"
            f"        (validation_id, _now, _now.strftime('%Y-%m-%d'), '{rel.name}', '{rel.from_table}', '{rel.from_column}',\n"
            f"         '{rel.to_table}', '{rel.to_column}', orphan_count, orphan_samples, validation_passed, _elapsed, None)\n"
            f"    ]\n"
            f"    \n"
            f"    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')\n"
            f"    \n"
            f"except Exception as e:\n"
            f"    logger.error(f'Error validating relationship: {{e}}')\n"
            f"    error_msg = str(e)\n"
            f"    _elapsed = (time.time() - _start_time) * 1000\n"
            f"    \n"
            f"    # Log error\n"
            f"    _now = datetime.now()\n"
            f"    result_data = [\n"
            f"        (validation_id, _now, _now.strftime('%Y-%m-%d'), '{rel.name}', '{rel.from_table}', '{rel.from_column}',\n"
            f"         '{rel.to_table}', '{rel.to_column}', -1, '', False, _elapsed, error_msg)\n"
            f"    ]\n"
            f"    \n"
            f"    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')\n"
        )
        return self._create_python_code_cell(code)


def generate_tmdl_validation_notebook(tmdl_path: Path) -> Dict[str, Any]:
    """Main function to generate validation notebook from TMDL files.
    
    Args:
        tmdl_path: Path to directory containing .tmdl files
        
    Returns:
        Notebook dictionary ready for JSON serialization
    """
    # Parse TMDL files
    parser = TMDLParser()
    tables, relationships = parser.parse_directory(tmdl_path)
    
    if not tables:
        logger.warning(f"No semantic model definitions found in {tmdl_path}")
        # Return minimal notebook
        return {
            "cells": [
                {
                    "cell_type": "markdown",
                    "metadata": {},
                    "source": [
                        "# Semantic Model Validation\n",
                        "\n",
                        "No semantic model definitions (.tmdl files) found in the specified path."
                    ]
                }
            ],
            "metadata": {
                "language_info": {"name": "python"},
                "kernelspec": {"name": "python3", "display_name": "Python 3"}
            },
            "nbformat": 4,
            "nbformat_minor": 2
        }
    
    # Generate validation notebook
    generator = ValidationNotebookGenerator(tables, relationships)
    notebook = generator.generate_notebook()
    
    logger.info(f"Generated validation notebook with {len(notebook['cells'])} cells")
    return notebook
