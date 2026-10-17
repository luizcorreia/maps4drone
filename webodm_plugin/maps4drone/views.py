"""Django REST views of the plugin: thin wrappers over logic.py and the maps4drone service."""

from app.plugins.views import TaskView
from django.http import HttpResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from maps4drone import service, thumbnail

from . import logic


def _error(message, code):
    return Response({"detail": message}, status=code)


class Drones(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        return Response(service.drones_payload())


class Camera(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        try:
            return Response(
                service.camera_payload(
                    request.query_params.get("drone", ""),
                    float(request.query_params.get("altitude", "")),
                    request.query_params.get("camera") or None,
                )
            )
        except ValueError as err:
            return _error(str(err), status.HTTP_422_UNPROCESSABLE_ENTITY)


class Import(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        try:
            return Response(
                service.import_payload(request.query_params.get("name", ""), request.body)
            )
        except ValueError as err:
            return _error(str(err), status.HTTP_422_UNPROCESSABLE_ENTITY)


class PlanView(TaskView):
    """Plan or export; with a task id the terrain comes from that task's DSM/DTM."""

    def _mission(self, request, pk):
        if not request.user.is_authenticated:
            return None, _error("entre no WebODM para planejar", status.HTTP_401_UNAUTHORIZED)
        task = self.get_and_check_task(request, pk) if pk else None
        try:
            req, layer = logic.parse_plan_body(request.data)
            elevation = logic.elevation_for(
                layer if req.params.terrain else None,
                task.available_assets if task else [],
                task.get_asset_download_path if task else None,
            )
            return service.build_mission(req, elevation), None
        except ValueError as err:
            return None, _error(str(err), status.HTTP_422_UNPROCESSABLE_ENTITY)
        except service.UpstreamError as err:
            return None, _error(str(err), status.HTTP_502_BAD_GATEWAY)


class Plan(PlanView):
    def post(self, request, pk=None):
        mission, error = self._mission(request, pk)
        return error or Response(service.plan_payload(mission))


class Export(PlanView):
    def post(self, request, pk=None):
        mission, error = self._mission(request, pk)
        if error:
            return error
        file = service.export_mission(mission, thumbnail.osm_tiles())
        response = HttpResponse(file.data, content_type=file.media_type)
        response["Content-Disposition"] = f'attachment; filename="{file.filename}"'
        return response


class TaskInfo(TaskView):
    def get(self, request, pk=None):
        task = self.get_and_check_task(request, pk)
        return Response(
            logic.task_info(
                str(task.id), task.project.id, task.name, task.get_extent(), task.available_assets
            )
        )
