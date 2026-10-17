"""What the plugin does, with no Django in it: parse a request, pick the terrain model.

The Django views in views.py only translate HTTP to and from these functions, which keeps
the behaviour testable without a WebODM around.
"""

from collections.abc import Sequence
from typing import Any, Callable, Optional

from maps4drone import service
from maps4drone.elevation import Elevation, open_meteo_elevation
from maps4drone.raster import raster_elevation

DEM_LAYERS = {"dsm": "dsm.tif", "dtm": "dtm.tif"}


def format_validation_error(err: Exception) -> str:
    """One readable line from a pydantic ValidationError (1.x and 2.x share errors())."""
    errors = getattr(err, "errors", None)
    if not callable(errors):
        return str(err)
    parts = []
    for item in errors():
        where = ".".join(str(p) for p in item.get("loc", ()) if p != "params")
        parts.append(
            f"{where}: {item.get('msg', 'valor invalido')}" if where else item.get("msg", "")
        )
    return "; ".join(parts) or str(err)


def parse_plan_body(data: dict[str, Any]) -> tuple[service.PlanRequest, Optional[str]]:
    """Split the plan request from the plugin's own `dem` choice ({"layer": "dsm"|"dtm"})."""
    body = dict(data)
    dem = body.pop("dem", None)
    layer = None
    if dem:
        layer = str(dem.get("layer", "dsm") if isinstance(dem, dict) else dem).lower()
        if layer not in DEM_LAYERS:
            raise ValueError(f"modelo de elevacao desconhecido: {layer} (use dsm ou dtm)")
    try:
        return service.PlanRequest(**body), layer
    except ValueError as err:
        raise ValueError(format_validation_error(err)) from err


def elevation_for(
    layer: Optional[str],
    available_assets: Sequence[str],
    asset_path: Optional[Callable[[str], str]],
) -> Elevation:
    """The task's own DSM/DTM when asked for, otherwise the online elevation service."""
    if layer is None:
        return open_meteo_elevation()
    asset = DEM_LAYERS[layer]
    if asset_path is None or asset not in available_assets:
        raise ValueError(
            f"a tarefa nao tem {layer.upper()}: processe-a com a opcao de gerar o modelo"
        )
    return raster_elevation(asset_path(asset))


def task_info(
    task_id: str,
    project_id: Any,
    name: str,
    extent: Optional[Sequence[float]],
    available_assets: Sequence[str],
) -> dict[str, Any]:
    """What the page needs to know about the task it was opened for."""
    return {
        "id": task_id,
        "project": project_id,
        "name": name,
        "extent": list(extent) if extent else None,  # [west, south, east, north]
        "assets": {
            "orthophoto": "orthophoto.tif" in available_assets,
            "dsm": "dsm.tif" in available_assets,
            "dtm": "dtm.tif" in available_assets,
        },
        "tiles": (
            f"/api/projects/{project_id}/tasks/{task_id}/orthophoto/tiles/{{z}}/{{x}}/{{y}}.png"
        ),
    }
