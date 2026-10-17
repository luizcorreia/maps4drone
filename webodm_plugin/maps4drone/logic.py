"""What the plugin does, with no Django in it: parse a request, pick the terrain model.

The Django views in views.py only translate HTTP to and from these functions, which keeps
the behaviour testable without a WebODM around.
"""

import json
from collections.abc import Sequence
from typing import Any, Callable, Optional, Protocol

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


# ---- saved flight plans -------------------------------------------------------------------
#
# A plan belongs to a WebODM project, not to a task: it is made before the photos exist, and
# only afterwards tied to the task that processed them. Plans of a project live in a single
# JSON list under one key of WebODM's plugin data store.

MAX_PLANS_PER_PROJECT = 200
MAX_NAME_LENGTH = 120
MAX_REQUEST_BYTES = 200_000
REQUEST_KEYS = ("mode", "geometry", "params", "dem")
PLANNED, FLOWN = "planned", "flown"


class PlanNotFound(LookupError):
    """There is no such plan in the project."""


class Store(Protocol):
    """The part of WebODM's DataStore the plans use."""

    def get_json(self, key: str, default: Any = ...) -> Any: ...

    def set_json(self, key: str, value: Any) -> Any: ...


def _key(project_id: Any) -> str:
    return f"plans:{project_id}"


def list_plans(store: Store, project_id: Any) -> list[dict[str, Any]]:
    """The project's plans, the most recently changed first."""
    plans = store.get_json(_key(project_id), [])
    plans = plans if isinstance(plans, list) else []
    return sorted(plans, key=lambda p: p.get("updated_at", ""), reverse=True)


def _stored_request(raw: Any) -> dict[str, Any]:
    """The plan request worth keeping: validated, and trimmed to the keys the planner reads."""
    if not isinstance(raw, dict):
        raise ValueError("o plano precisa do pedido de planejamento (modo, geometria e parametros)")
    req, _ = parse_plan_body(raw)
    if req.geometry is None:
        raise ValueError("desenhe a area ou o trajeto antes de salvar o plano")
    request = {k: raw[k] for k in REQUEST_KEYS if raw.get(k) is not None}
    if len(json.dumps(request)) > MAX_REQUEST_BYTES:
        raise ValueError("o plano e grande demais para ser salvo")
    return request


def save_plan(
    store: Store, project_id: Any, body: Any, username: str, now: str, new_id: str
) -> dict[str, Any]:
    """Create a plan, or update the one named by body["id"]; a saved plan keeps its task link."""
    if not isinstance(body, dict):
        raise ValueError("pedido invalido")
    name = str(body.get("name") or "").strip()
    if not name:
        raise ValueError("de um nome ao plano")
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(f"o nome do plano passa de {MAX_NAME_LENGTH} caracteres")
    request = _stored_request(body.get("request"))

    plans = list_plans(store, project_id)
    existing = None
    if body.get("id"):
        existing = next((p for p in plans if p["id"] == body["id"]), None)
        if existing is None:
            raise PlanNotFound(body["id"])
    elif len(plans) >= MAX_PLANS_PER_PROJECT:
        raise ValueError(f"o projeto ja tem {MAX_PLANS_PER_PROJECT} planos: apague algum")

    plan = {
        "id": existing["id"] if existing else new_id,
        "name": name,
        "request": request,
        "status": existing["status"] if existing else PLANNED,
        "task_id": existing.get("task_id") if existing else None,
        "created_at": existing["created_at"] if existing else now,
        "created_by": existing["created_by"] if existing else username,
        "updated_at": now,
        "updated_by": username,
    }
    store.set_json(_key(project_id), [plan] + [p for p in plans if p is not existing])
    return plan


def delete_plan(store: Store, project_id: Any, plan_id: str) -> None:
    plans = list_plans(store, project_id)
    kept = [p for p in plans if p["id"] != plan_id]
    if len(kept) == len(plans):
        raise PlanNotFound(plan_id)
    store.set_json(_key(project_id), kept)


def link_plan(
    store: Store, project_id: Any, plan_id: str, task_id: Optional[str], now: str, username: str
) -> dict[str, Any]:
    """Tie the plan to the task that processed its photos (or, with None, untie it)."""
    plans = list_plans(store, project_id)
    plan = next((p for p in plans if p["id"] == plan_id), None)
    if plan is None:
        raise PlanNotFound(plan_id)
    plan = {
        **plan,
        "task_id": task_id,
        "status": FLOWN if task_id else PLANNED,
        "updated_at": now,
        "updated_by": username,
    }
    store.set_json(_key(project_id), [plan] + [p for p in plans if p["id"] != plan_id])
    return plan
