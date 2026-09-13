"""Copy library notebooks into output, replacing the default lakehouse name."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Optional

from ..utils.logging import get_logger

logger = get_logger(__name__)

# Path segment that groups per-version CONFIG leaf notebooks:
#   libraries/UTL/CONFIG/_functions/v1/nb_config_*.Notebook/...
#   libraries/UTL/CONFIG/_functions/v2/nb_config_*.Notebook/...
_CONFIG_FUNCTIONS = ("CONFIG", "_functions")
_VERSION_RE = re.compile(r"^v(\d+)$")


def _resolve_config_version(source_utl: Path, requested: Optional[str]) -> Optional[str]:
    """Return the config version subfolder to use, or None if the layout isn't versioned yet."""
    functions_root = source_utl / "CONFIG" / "_functions"
    if not functions_root.exists():
        return None
    available = sorted(
        (p.name for p in functions_root.iterdir() if p.is_dir() and _VERSION_RE.match(p.name)),
        key=lambda n: int(_VERSION_RE.match(n).group(1)),
    )
    if not available:
        return None
    if requested:
        if requested not in available:
            raise FileNotFoundError(
                f"CONFIG version '{requested}' not found under {functions_root}. "
                f"Available: {', '.join(available)}"
            )
        return requested
    return available[-1]


def _map_config_path(rel: Path, selected_version: Optional[str]) -> Optional[Path]:
    """Return the output-relative path for a source path under CONFIG/_functions,
    or None if the file belongs to a different (unselected) version and should be skipped.

    For files outside CONFIG/_functions this returns rel unchanged.
    Version segment is stripped from the output path so deployed layout stays flat:
      CONFIG/_functions/v1/nb_config_bootstrap.Notebook/x  ->  CONFIG/_functions/nb_config_bootstrap.Notebook/x
    """
    parts = rel.parts
    if len(parts) < 3 or parts[:2] != _CONFIG_FUNCTIONS:
        return rel
    version_seg = parts[2]
    if not _VERSION_RE.match(version_seg):
        return rel  # unversioned file under _functions/ (e.g. a README) — copy as-is
    if selected_version and version_seg != selected_version:
        return None
    return Path(*_CONFIG_FUNCTIONS, *parts[3:])


# The configure cell block that gets injected when a notebook has no %%configure cell
_CONFIGURE_CELL_TEMPLATE = """\
# CELL ********************

# MAGIC %%configure
# MAGIC {{
# MAGIC   "defaultLakehouse": {{
# MAGIC     "name": "{lakehouse_name}"
# MAGIC   }}
# MAGIC }}

# METADATA ********************

# META {{
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }}

"""

# Regex that matches the lakehouse name inside a %%configure cell:
#   # MAGIC     "name": "<anything>"
_LKH_NAME_RE = re.compile(
    r'^(# MAGIC\s+"name":\s+")([^"]+)(".*)',
    re.MULTILINE,
)


def copy_library_notebooks(
    output_dir: Path,
    lakehouse_name: str,
    libraries_dir: Optional[Path] = None,
    config_version: Optional[str] = None,
) -> int:
    """Copy libraries/UTL into output/notebooks, replacing the default lakehouse.

    For every ``notebook-content.py`` found under *libraries_dir*/UTL:
    * If a ``%%configure`` cell already exists, replace the lakehouse ``"name"`` value.
    * If no ``%%configure`` cell exists, prepend one as the first cell.
    All other files (e.g. ``.platform``) and empty directories are copied as-is.

    CONFIG leaves live under ``libraries/UTL/CONFIG/_functions/v<N>/``. Only the selected
    version is copied; the version segment is stripped from the output path so the
    deployed layout stays flat (``UTL/CONFIG/_functions/nb_config_*.Notebook``).

    Args:
        output_dir: Root output directory (e.g. ``output/``).
        lakehouse_name: Lakehouse name to inject (e.g. ``lkh_001``).
        libraries_dir: Root of library notebooks.  Defaults to
            ``<project_root>/libraries`` (auto-detected from this file's
            location).
        config_version: CONFIG functions version to include (e.g. ``v1``). If ``None``,
            the highest available ``v<N>`` is used.

    Returns:
        Number of notebook files processed.
    """
    if libraries_dir is None:
        # Resolve: this file -> generators/ -> northstar_formation/ -> src/ -> northstar-formation/
        project_root = Path(__file__).resolve().parents[3]
        libraries_dir = project_root / "libraries"

    source_utl = libraries_dir / "UTL"
    if not source_utl.exists():
        logger.warning(f"Library directory not found: {source_utl}")
        return 0

    selected_version = _resolve_config_version(source_utl, config_version)
    if selected_version:
        logger.info(f"CONFIG functions version: {selected_version}")

    dest_utl = output_dir / "notebooks" / "UTL"
    count = 0

    for src_path in source_utl.rglob("*"):
        rel = src_path.relative_to(source_utl)

        # Fabric ALM treats every file under a .Notebook item as a definition
        # part and rejects empty .pyc payloads with
        # "This item type doesn't support definition parts with empty payload."
        if "__pycache__" in src_path.parts:
            continue

        mapped = _map_config_path(rel, selected_version)
        if mapped is None:
            continue
        dst_path = dest_utl / mapped

        if src_path.is_dir():
            dst_path.mkdir(parents=True, exist_ok=True)
            continue

        # Ensure parent dir exists
        dst_path.parent.mkdir(parents=True, exist_ok=True)

        if src_path.name == "notebook-content.py":
            _copy_notebook_content(src_path, dst_path, lakehouse_name)
            count += 1
        elif src_path.suffix.lower() == ".json" and src_path.parent.suffix == ".Notebook":
            # Fabric ALM notebook publish rejects arbitrary .json parts under .Notebook items.
            logger.debug(f"Skipping unsupported notebook part: {src_path}")
            continue
        else:
            shutil.copy2(src_path, dst_path)

    # Also create any empty directories that rglob("*") skips
    for src_dir in source_utl.rglob("*"):
        if src_dir.is_dir():
            if "__pycache__" in src_dir.parts:
                continue
            mapped = _map_config_path(src_dir.relative_to(source_utl), selected_version)
            if mapped is None:
                continue
            (dest_utl / mapped).mkdir(parents=True, exist_ok=True)

    logger.info(
        f"Copied {count} library notebook(s) to {dest_utl} "
        f"with lakehouse '{lakehouse_name}'"
    )
    return count


def copy_auth_files(
    output_dir: Path,
    lakehouse_name: str,
    auth_dir: Optional[Path] = None,
) -> int:
    """Copy northstar-formation/auth (auth notebooks + pl_auth pipeline) into every
    customer's output, as a SIBLING of the ENG output (i.e. output_<customer>/auth,
    not output_<customer>/ENG/notebooks/auth) - so it deploys as its own
    top-level item set alongside ENG's notebooks/pipelines, not nested inside
    them.

    Notebook lakehouse names are patched the same way copy_library_notebooks
    does it. pl_auth.DataPipeline's notebookId references use logical IDs
    (from each auth notebook's own .platform), not real GUIDs - fabric-cicd
    resolves those to real deployed item IDs at publish time automatically
    (same mechanism as every other generated pipeline in this project), as
    long as the referenced notebooks are deployed in the same publish. Do not
    replace them with real IDs from any specific workspace - that would only
    work for whichever workspace they were copied from.

    Args:
        output_dir: The ENG output directory (e.g. output_<customer>/ENG) -
            auth is written to its parent, not inside it.
        lakehouse_name: Lakehouse name to inject into auth notebooks' %%configure cells.
        auth_dir: Root of the auth source folder. Defaults to
            <project_root>/auth (auto-detected from this file's location).

    Returns:
        Number of notebook files processed (the pipeline is copied unconditionally
        alongside them, not counted here).
    """
    if auth_dir is None:
        project_root = Path(__file__).resolve().parents[3]
        auth_dir = project_root / "auth"

    if not auth_dir.exists():
        logger.warning(f"Auth directory not found: {auth_dir}")
        return 0

    dest_auth = output_dir.parent / "auth"
    count = 0

    for src_path in auth_dir.rglob("*"):
        if "__pycache__" in src_path.parts:
            continue

        rel = src_path.relative_to(auth_dir)
        dst_path = dest_auth / rel

        if src_path.is_dir():
            dst_path.mkdir(parents=True, exist_ok=True)
            continue

        dst_path.parent.mkdir(parents=True, exist_ok=True)

        if src_path.name == "notebook-content.py":
            _copy_notebook_content(src_path, dst_path, lakehouse_name)
            count += 1
        elif src_path.suffix.lower() == ".json" and src_path.parent.suffix == ".Notebook":
            # Same Fabric ALM restriction as copy_library_notebooks - arbitrary
            # .json parts under .Notebook items get rejected on publish.
            logger.debug(f"Skipping unsupported notebook part: {src_path}")
            continue
        else:
            shutil.copy2(src_path, dst_path)

    logger.info(f"Copied auth folder ({count} notebook(s) + pl_auth pipeline) to {dest_auth}")
    return count


def copy_demo_data_files(
    output_dir: Path,
    lakehouse_name: str,
    demo_data_dir: Path,
) -> int:
    """Copy a customer's demo_data notebooks + wrapper pipeline into
    output_dir/demo_data (nested, unlike auth/ which is a sibling of the
    engineering output - demo_data is itself an engineering artifact, so it
    lives under data_engineering/ alongside notebooks/pipelines).

    Args:
        output_dir: The data_engineering output directory - demo_data is
            written to output_dir/demo_data.
        lakehouse_name: Lakehouse name to inject into demo_data notebooks'
            %%configure cells.
        demo_data_dir: Source demo_data folder, e.g.
            models/customers/<customer>/demo_data. Customer-specific (unlike
            auth/, which is shared across all customers), so callers must
            resolve this themselves rather than relying on auto-detection.

    Returns:
        Number of notebook files processed (pipelines are copied
        unconditionally alongside them, not counted here).
    """
    if not demo_data_dir.exists():
        logger.info(f"No demo_data folder for this customer: {demo_data_dir}")
        return 0

    dest = output_dir / "demo_data"
    count = 0

    for src_path in demo_data_dir.rglob("*"):
        if "__pycache__" in src_path.parts:
            continue

        rel = src_path.relative_to(demo_data_dir)
        dst_path = dest / rel

        if src_path.is_dir():
            dst_path.mkdir(parents=True, exist_ok=True)
            continue

        dst_path.parent.mkdir(parents=True, exist_ok=True)

        if src_path.name == "notebook-content.py":
            _copy_notebook_content(src_path, dst_path, lakehouse_name)
            count += 1
        elif src_path.suffix.lower() == ".json" and src_path.parent.suffix == ".Notebook":
            logger.debug(f"Skipping unsupported notebook part: {src_path}")
            continue
        else:
            shutil.copy2(src_path, dst_path)

    logger.info(f"Copied demo_data folder ({count} notebook(s)) to {dest}")
    return count


def write_lakehouse_placeholder(
    output_dir: Path,
    lakehouse_name: str,
) -> Path:
    """Write a minimal .Lakehouse folder (just .platform, no definition/ - a
    Lakehouse has no git-syncable definition content) under
    output_dir/lakehouses/, for organizational visibility in the generated
    output tree.

    This is a documentation/reference placeholder only - it is deliberately
    NOT added to any customer's item_types_in_scope in config.yml. Fabric
    Lakehouses in this project are Terraform-managed (terraform/fabric_lakehouse.tf),
    not fabric-cicd-managed; including "Lakehouse" in scope risks fabric-cicd
    treating the Terraform-created Lakehouse as an orphan to delete during
    cleanup (see docs/fabric-environment-setup-log.md). Deployment behavior
    is unchanged by this folder's presence.
    """
    import uuid as _uuid

    lh_dir = output_dir / "lakehouses" / f"{lakehouse_name}.Lakehouse"
    lh_dir.mkdir(parents=True, exist_ok=True)
    platform = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Lakehouse", "displayName": lakehouse_name},
        "config": {
            "version": "2.0",
            "logicalId": str(_uuid.uuid5(_uuid.NAMESPACE_DNS, lakehouse_name.strip().lower())),
        },
    }
    (lh_dir / ".platform").write_text(json.dumps(platform, indent=2), encoding="utf-8")
    logger.info(f"Wrote Lakehouse placeholder (reference only, not deployed) to {lh_dir}")
    return lh_dir


def _copy_notebook_content(
    src: Path,
    dst: Path,
    lakehouse_name: str,
) -> None:
    """Read a notebook-content.py, patch the lakehouse name, and write to *dst*."""
    content = src.read_text(encoding="utf-8")

    if "%%configure" in content:
        # Replace the lakehouse name inside the existing %%configure cell
        new_content = _LKH_NAME_RE.sub(
            rf'\g<1>{lakehouse_name}\3',
            content,
        )
        dst.write_text(new_content, encoding="utf-8")
    else:
        # No configure cell – copy as-is.  These are utility notebooks
        # invoked via %run from other notebooks; injecting %%configure
        # would cause MagicUsageError because the session is already active.
        dst.write_text(content, encoding="utf-8")


def _find_first_cell_position(content: str) -> int:
    """Find the position right after the notebook-level METADATA block.

    The configure cell must be the very first cell — before any CELL or
    MARKDOWN blocks.  We insert right after the closing ``# META }`` of
    the notebook header.
    """
    # Find the end of the notebook-level metadata (first # META } line)
    meta_end = re.search(r"^# META \}$", content, re.MULTILINE)
    if meta_end:
        # Insert after the META } line plus its trailing newline(s)
        pos = meta_end.end()
        # Skip any blank lines between the metadata and the first cell
        while pos < len(content) and content[pos] == "\n":
            pos += 1
        return pos
    # Last resort: beginning of file
    return 0
