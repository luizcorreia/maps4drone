"""Django REST views of the plugin: thin wrappers over logic.py and the maps4drone service."""

import uuid
from datetime import datetime, timezone

from app.api.common import get_and_check_project
from app.models import PluginDatum, Task
from app.plugins import GlobalDataStore
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


PLUGIN = "maps4drone"


class _PlanStore:
    """GlobalDataStore plus the two things the plans need that it lacks: list by prefix, delete."""

    def __init__(self):
        self._store = GlobalDataStore(PLUGIN)

    def get_json(self, key, default=None):
        return self._store.get_json(key, default)

    def set_json(self, key, value):
        return self._store.set_json(key, value)

    def del_key(self, key):
        return self._store.del_key(key)

    def items(self, prefix):
        rows = PluginDatum.objects.filter(user=None, key__startswith=self._store.db_key(prefix))
        return list(rows.values_list("json_value", flat=True))


def _store():
    return _PlanStore()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _answer(call):
    """Run a plan-store call and turn its failures into HTTP answers."""
    try:
        return Response(call())
    except logic.PlanNotFound:
        return _error("plano nao encontrado", status.HTTP_404_NOT_FOUND)
    except ValueError as err:
        return _error(str(err), status.HTTP_422_UNPROCESSABLE_ENTITY)


class ProjectPlans(APIView):
    """GET lists the project's saved plans; POST saves one (with an id: updates it)."""

    permission_classes = (IsAuthenticated,)

    def get(self, request, pk=None):
        project = get_and_check_project(request, pk)
        return Response(logic.list_plans(_store(), project.id))

    def post(self, request, pk=None):
        project = get_and_check_project(request, pk, perms=("change_project",))
        return _answer(
            lambda: logic.save_plan(
                _store(), project.id, request.data, request.user.username, _now(), uuid.uuid4().hex
            )
        )


class ProjectPlan(APIView):
    permission_classes = (IsAuthenticated,)

    def delete(self, request, pk=None, plan_id=None):
        project = get_and_check_project(request, pk, perms=("change_project",))
        return _answer(
            lambda: logic.delete_plan(_store(), project.id, plan_id) or {"deleted": plan_id}
        )


class ProjectPlanTask(APIView):
    """POST {"task": "<id>"} ties the plan to a task of the same project; null unties it."""

    permission_classes = (IsAuthenticated,)

    def post(self, request, pk=None, plan_id=None):
        project = get_and_check_project(request, pk, perms=("change_project",))
        task_id = request.data.get("task") if hasattr(request.data, "get") else None
        if task_id:
            try:
                task_id = str(uuid.UUID(str(task_id)))  # Task.pk is a UUID: anything else is a 422
            except ValueError:
                return _error("tarefa invalida", status.HTTP_422_UNPROCESSABLE_ENTITY)
            if not Task.objects.filter(pk=task_id, project=project).exists():
                return _error(
                    "a tarefa nao pertence a este projeto", status.HTTP_422_UNPROCESSABLE_ENTITY
                )
        return _answer(
            lambda: logic.link_plan(
                _store(), project.id, plan_id, task_id or None, _now(), request.user.username
            )
        )
