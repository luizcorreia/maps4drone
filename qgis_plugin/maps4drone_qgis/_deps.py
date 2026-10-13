"""Locate the maps4drone core, preferring the copy vendored next to the plugin."""

import importlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_PIP = "python -m pip install shapely pyproj"


def ensure_core() -> str | None:
    """Make the core importable. Returns None on success, else a human-readable problem."""
    if sys.version_info < (3, 10):  # noqa: UP036 - QGIS 3.28 can still ship Python 3.9
        return (
            f"maps4drone needs Python 3.10 or newer, but this QGIS runs "
            f"Python {sys.version_info[0]}.{sys.version_info[1]}."
        )
    vendor = HERE / "vendor"
    if vendor.is_dir() and str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))
    for module in ("shapely", "pyproj", "maps4drone"):
        try:
            importlib.import_module(module)
        except Exception as err:  # noqa: BLE001 - any failure must become a message, not a crash
            hint = f"\n\nInstall it with QGIS's Python:\n  {_PIP}" if module != "maps4drone" else ""
            return f"Could not import '{module}': {err}{hint}"
    import shapely

    if int(shapely.__version__.split(".")[0]) < 2:
        return f"shapely>=2 is required, found {shapely.__version__}.\n\n  {_PIP} --upgrade"
    return None
