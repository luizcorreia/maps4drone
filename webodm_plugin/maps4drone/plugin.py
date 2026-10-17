import os
import sys

from app.plugins import Menu, MountPoint, PluginBase

HERE = os.path.dirname(os.path.abspath(__file__))
VENDOR = os.path.join(HERE, "vendor")  # the maps4drone core, copied in by the build script


class Plugin(PluginBase):
    def __init__(self):
        super().__init__()
        if VENDOR not in sys.path:
            sys.path.insert(0, VENDOR)

    def main_menu(self):
        return [Menu("Planejar voo", self.public_url("index.html"), "fa fa-plane fa-fw")]

    def include_js_files(self):
        return ["main.js"]

    def serve_public_assets(self, request):
        # main.js is loaded on every page, public shares included; the planner is for users
        return request.user.is_authenticated or request.path.endswith("/main.js")

    def api_mount_points(self):
        # shapely may live in the plugin's own site-packages (see requirements.txt)
        with self.python_imports():
            from . import views

        return [
            MountPoint(r"drones$", views.Drones.as_view()),
            MountPoint(r"camera$", views.Camera.as_view()),
            MountPoint(r"import$", views.Import.as_view()),
            MountPoint(r"plan$", views.Plan.as_view()),
            MountPoint(r"export$", views.Export.as_view()),
            MountPoint(r"task/(?P<pk>[^/.]+)/info$", views.TaskInfo.as_view()),
            MountPoint(r"task/(?P<pk>[^/.]+)/plan$", views.Plan.as_view()),
            MountPoint(r"task/(?P<pk>[^/.]+)/export$", views.Export.as_view()),
            MountPoint(r"project/(?P<pk>[^/.]+)/plans$", views.ProjectPlans.as_view()),
            MountPoint(
                r"project/(?P<pk>[^/.]+)/plans/(?P<plan_id>[0-9a-f]+)$", views.ProjectPlan.as_view()
            ),
            MountPoint(
                r"project/(?P<pk>[^/.]+)/plans/(?P<plan_id>[0-9a-f]+)/task$",
                views.ProjectPlanTask.as_view(),
            ),
        ]
