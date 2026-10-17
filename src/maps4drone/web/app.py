"""Web API and static UI for planning missions in the browser."""

import argparse
from pathlib import Path
from typing import Annotated, Any, Optional

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import service, thumbnail
from ..elevation import Elevation, open_meteo_elevation
from ..service import PlanRequest

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="maps4drone")


@app.exception_handler(ValueError)
async def _value_error(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(service.UpstreamError)
async def _upstream_error(_: Request, exc: service.UpstreamError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})


def get_elevation() -> Elevation:
    return open_meteo_elevation()


def get_tiles() -> thumbnail.TileFetcher:
    return thumbnail.osm_tiles()


@app.get("/api/drones")
def drones() -> list[dict[str, Any]]:
    return service.drones_payload()


@app.get("/api/camera")
def camera_info(drone: str, altitude: float, camera: Optional[str] = None) -> dict[str, float]:
    return service.camera_payload(drone, altitude, camera)


@app.post("/api/plan")
def plan(
    req: PlanRequest, elevation: Annotated[Elevation, Depends(get_elevation)]
) -> dict[str, Any]:
    return service.plan_payload(service.build_mission(req, elevation))


@app.post("/api/export")
def export(
    req: PlanRequest,
    elevation: Annotated[Elevation, Depends(get_elevation)],
    tiles: Annotated[thumbnail.TileFetcher, Depends(get_tiles)],
) -> Response:
    file = service.export_mission(service.build_mission(req, elevation), tiles)
    return Response(
        file.data,
        media_type=file.media_type,
        headers={"Content-Disposition": f'attachment; filename="{file.filename}"'},
    )


@app.post("/api/import")
async def import_file(request: Request, name: str) -> dict[str, Any]:
    """Raw file body (.kml/.kmz/.geojson); returns the first polygon and/or line found."""
    return service.import_payload(name, await request.body())


NOT_BUILT = """<!doctype html><meta charset="utf-8"><title>maps4drone</title>
<body style="font-family:system-ui;max-width:40rem;margin:4rem auto;padding:0 1rem">
<h1>Interface ainda n&atilde;o compilada</h1>
<p>A API est&aacute; no ar (<a href="/docs">/docs</a>), mas falta o build da interface:</p>
<pre>cd web &amp;&amp; npm ci &amp;&amp; npm run build</pre>
<p>Para desenvolver, rode <code>npm run dev</code> em <code>web/</code>.</p>"""


def mount_ui(target: FastAPI, directory: Path = STATIC) -> None:
    """Serve the compiled React app, or a pointer to how to build it."""
    if (directory / "index.html").is_file():
        target.mount("/", StaticFiles(directory=directory, html=True), name="ui")
    else:

        @target.get("/", include_in_schema=False)
        def not_built() -> HTMLResponse:
            return HTMLResponse(NOT_BUILT)


mount_ui(app)


def main() -> None:
    import uvicorn

    ap = argparse.ArgumentParser(prog="maps4drone-web")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)
