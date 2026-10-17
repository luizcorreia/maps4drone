"""Processing algorithms. Thin wrappers: read QGIS inputs, call the core, emit QGIS outputs."""

import math
from pathlib import Path
from typing import Any

from qgis.core import (
    NULL,
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingOutputString,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterPoint,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterString,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QCoreApplication

from maps4drone import atom2
from maps4drone.camera import load_drones
from maps4drone.planners.corridor import plan_corridor
from maps4drone.planners.facade import plan_facade
from maps4drone.planners.orbit import plan_orbit
from maps4drone.planners.survey import SurveyParams, plan_survey
from maps4drone.stats import estimate

from .geometry import (
    ROUTE_FIELDS,
    WAYPOINT_FIELDS,
    first_line,
    polygons_from_rings,
    route_coords,
    route_row,
    summary_text,
    waypoint_rows,
)

WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")
DRONES = load_drones()
DRONE_IDS = list(DRONES)


def _enum(owner: Any, scope: str, member: str) -> Any:
    """Enum member that works with both scoped (QGIS 4) and flat (QGIS 3.28) enums."""
    scoped = getattr(owner, scope, None)
    if scoped is not None and hasattr(scoped, member):
        return getattr(scoped, member)
    return getattr(owner, member)


def _wkb(name: str) -> Any:
    scoped = getattr(Qgis, "WkbType", None)
    return getattr(scoped, name) if scoped is not None else getattr(QgsWkbTypes, name)


def _field_type(kind: str) -> Any:
    if Qgis.QGIS_VERSION_INT >= 33800:
        from qgis.PyQt.QtCore import QMetaType

        return {
            "int": QMetaType.Type.Int,
            "double": QMetaType.Type.Double,
            "string": QMetaType.Type.QString,
        }[kind]
    from qgis.PyQt.QtCore import QVariant

    return {"int": QVariant.Int, "double": QVariant.Double, "string": QVariant.String}[kind]


def _fields(spec: list[tuple[str, str]]) -> QgsFields:
    fields = QgsFields()
    for name, kind in spec:
        fields.append(QgsField(name, _field_type(kind)))
    return fields


def _number(
    name: str,
    label: str,
    default: float | None,
    low: float | None = None,
    high: float | None = None,
    integer: bool = False,
    optional: bool = False,
) -> Any:
    kind = _enum(QgsProcessingParameterNumber, "Type", "Integer" if integer else "Double")
    param = QgsProcessingParameterNumber(name, label, kind, default, optional)
    if low is not None:
        param.setMinimum(low)
    if high is not None:
        param.setMaximum(high)
    return param


def _source_types(kind: str) -> list[Any]:
    return [_enum(QgsProcessing, "SourceType", kind)]


class _Base(QgsProcessingAlgorithm):
    """Shared parameters (drone, outputs) and the output writing."""

    def tr(self, text: str) -> str:
        return QCoreApplication.translate("maps4drone", text)

    def createInstance(self) -> "_Base":  # noqa: N802
        return type(self)()

    def flags(self) -> Any:
        # pyproj creating CRS objects on a Processing worker thread crashes QGIS 4 (SIGSEGV
        # in libproj), so run on the main thread.
        scoped = getattr(Qgis, "ProcessingAlgorithmFlag", None)
        flag = scoped.NoThreading if scoped else QgsProcessingAlgorithm.FlagNoThreading
        return super().flags() | flag

    def group(self) -> str:
        return self.tr("Mapping")

    def groupId(self) -> str:  # noqa: N802
        return "mapping"

    def _drone_params(self) -> None:
        self.addParameter(
            QgsProcessingParameterEnum(
                "DRONE", self.tr("Drone"), [d.name for d in DRONES.values()], defaultValue=0
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                "CAMERA", self.tr("Camera (blank = drone default)"), optional=True
            )
        )

    def _survey_params(self) -> None:
        self.addParameter(_number("ALTITUDE", self.tr("Height above ground (m)"), 100, 5, 500))
        self.addParameter(_number("FRONT", self.tr("Front overlap (%)"), 80, 10, 95))
        self.addParameter(_number("SIDE", self.tr("Side overlap (%)"), 70, 10, 95))
        self.addParameter(_number("INTERVAL", self.tr("Camera shooting interval (s)"), 3, 1, 60))
        self.addParameter(_number("PITCH", self.tr("Gimbal pitch (deg)"), -90, -90, 20))
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                "DEM", self.tr("DEM for terrain following (optional)"), optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterPoint(
                "TAKEOFF", self.tr("Takeoff point (required with a DEM)"), optional=True
            )
        )
        self.addParameter(
            _number("TERRAIN_STEP", self.tr("Terrain sample spacing (m)"), 30, 5, 500)
        )

    def _output_params(self) -> None:
        self.addParameter(
            QgsProcessingParameterBoolean(
                "LEGACY", self.tr("Append legacy POI list (old firmware)"), defaultValue=False
            )
        )
        self.addParameter(
            QgsProcessingParameterFolderDestination(
                "MISSION_DIR",
                self.tr("Write new mission folder in (optional)"),
                optional=True,
                createByDefault=False,
            )
        )
        self.addParameter(
            QgsProcessingParameterFile(
                "REPLACE_DIR",
                self.tr("Overwrite this existing Atom 2 mission folder (optional)"),
                behavior=_enum(QgsProcessingParameterFile, "Behavior", "Folder"),
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                "OUTPUT_LINES",
                self.tr("Flight line"),
                _enum(QgsProcessing, "SourceType", "TypeVectorLine"),
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                "OUTPUT_POINTS",
                self.tr("Waypoints"),
                _enum(QgsProcessing, "SourceType", "TypeVectorPoint"),
            )
        )
        self.addOutput(QgsProcessingOutputString("MISSION_FOLDER", self.tr("Mission folder")))
        self.addOutput(QgsProcessingOutputString("SUMMARY", self.tr("Summary")))

    def _drone(self, parameters: dict, context: Any) -> tuple[Any, Any]:
        drone = DRONES[DRONE_IDS[self.parameterAsEnum(parameters, "DRONE", context)]]
        name = (self.parameterAsString(parameters, "CAMERA", context) or "").strip()
        try:
            return drone, drone.camera(name or None)
        except ValueError as err:
            raise QgsProcessingException(str(err)) from err

    def _lonlat(self, parameters: dict, name: str, context: Any) -> tuple[float, float]:
        point = self.parameterAsPoint(parameters, name, context, WGS84)
        return point.x(), point.y()

    def _survey_params_value(self, parameters: dict, context: Any, **extra: Any) -> SurveyParams:
        return SurveyParams(
            altitude_m=self.parameterAsDouble(parameters, "ALTITUDE", context),
            front_overlap=self.parameterAsDouble(parameters, "FRONT", context) / 100,
            side_overlap=self.parameterAsDouble(parameters, "SIDE", context) / 100,
            interval_s=self.parameterAsDouble(parameters, "INTERVAL", context),
            gimbal_pitch=self.parameterAsDouble(parameters, "PITCH", context),
            terrain_step_m=self.parameterAsDouble(parameters, "TERRAIN_STEP", context),
            **extra,
        )

    def _terrain(self, parameters: dict, context: Any) -> tuple[Any, Any]:
        """(elevation callable, takeoff lon/lat) from the optional DEM and takeoff point."""
        layer = self.parameterAsRasterLayer(parameters, "DEM", context)
        if layer is None:
            return None, None
        if parameters.get("TAKEOFF") in (None, ""):
            raise QgsProcessingException(self.tr("Terrain following needs a takeoff point."))
        to_dem = QgsCoordinateTransform(WGS84, layer.crs(), context.transformContext())
        provider = layer.dataProvider()

        def lookup(points: Any) -> list[float]:
            out = []
            for lon, lat in points:
                value, ok = provider.sample(to_dem.transform(QgsPointXY(lon, lat)), 1)
                if not ok or value is None or math.isnan(value):
                    raise QgsProcessingException(
                        self.tr("The DEM has no data at lon {0:.6f}, lat {1:.6f}.").format(lon, lat)
                    )
                out.append(float(value))
            return out

        return lookup, self._lonlat(parameters, "TAKEOFF", context)

    def _emit(self, mission: Any, parameters: dict, context: Any, feedback: Any) -> dict:
        stats = estimate(mission)
        route_fields, point_fields = _fields(ROUTE_FIELDS), _fields(WAYPOINT_FIELDS)
        line_sink, line_id = self.parameterAsSink(
            parameters, "OUTPUT_LINES", context, route_fields, _wkb("LineString"), WGS84
        )
        point_sink, point_id = self.parameterAsSink(
            parameters, "OUTPUT_POINTS", context, point_fields, _wkb("Point"), WGS84
        )
        if line_sink is None or point_sink is None:
            raise QgsProcessingException(self.tr("Could not create the output layers."))

        route = QgsFeature(route_fields)
        route.setGeometry(
            QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in route_coords(mission)])
        )
        route.setAttributes(list(route_row(mission, stats)))
        line_sink.addFeature(route)
        for row, (x, y) in zip(waypoint_rows(mission), route_coords(mission), strict=True):
            feature = QgsFeature(point_fields)
            feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
            feature.setAttributes(list(row))
            point_sink.addFeature(feature)

        folder = ""
        legacy = self.parameterAsBoolean(parameters, "LEGACY", context)
        replace = self.parameterAsString(parameters, "REPLACE_DIR", context)
        target = self.parameterAsString(parameters, "MISSION_DIR", context)
        try:
            if replace:
                folder = str(atom2.replace_mission(mission, Path(replace), legacy))
            elif target:
                folder = str(atom2.write_mission(mission, Path(target), legacy_poi_list=legacy))
        except (ValueError, OSError) as err:
            raise QgsProcessingException(str(err)) from err

        text = summary_text(mission, stats)
        feedback.pushInfo(text)
        for warning in mission.warnings:
            feedback.pushWarning(warning)
        if folder:
            feedback.pushInfo(f"mission   : {folder}")
        return {
            "OUTPUT_LINES": line_id,
            "OUTPUT_POINTS": point_id,
            "MISSION_FOLDER": folder,
            "SUMMARY": text,
        }

    def _plan(self, call: Any, *args: Any) -> Any:
        try:
            return call(*args)
        except ValueError as err:
            raise QgsProcessingException(str(err)) from err


def _polygons(source: Any, context: Any) -> list[list[list[tuple[float, float]]]]:
    to_wgs = QgsCoordinateTransform(source.sourceCrs(), WGS84, context.transformContext())
    polygons = []
    for feature in source.getFeatures():
        geom = QgsGeometry(feature.geometry())
        geom.transform(to_wgs)
        parts = geom.asMultiPolygon() if geom.isMultipart() else [geom.asPolygon()]
        polygons.extend([[(p.x(), p.y()) for p in ring] for ring in part] for part in parts)
    return polygons


def _lines(source: Any, context: Any) -> list[list[tuple[float, float]]]:
    to_wgs = QgsCoordinateTransform(source.sourceCrs(), WGS84, context.transformContext())
    lines = []
    for feature in source.getFeatures():
        geom = QgsGeometry(feature.geometry())
        geom.transform(to_wgs)
        parts = geom.asMultiPolyline() if geom.isMultipart() else [geom.asPolyline()]
        lines.extend([(p.x(), p.y()) for p in part] for part in parts)
    return lines


class SurveyGridAlgorithm(_Base):
    def name(self) -> str:
        return "survey_grid"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("Survey grid")

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "Lawn-mower survey over polygons (optionally a second perpendicular pass), with "
            "optional terrain following from a DEM. Speed comes from the shooting interval and "
            "front overlap; set the same interval in the drone app's camera timer."
        )

    def initAlgorithm(self, config: Any = None) -> None:  # noqa: N802
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                "INPUT", self.tr("Area to map"), _source_types("TypeVectorPolygon")
            )
        )
        self._drone_params()
        self._survey_params()
        self.addParameter(
            _number(
                "ANGLE",
                self.tr("Flight line bearing (deg, 0 = north; blank = long axis)"),
                None,
                0,
                360,
                optional=True,
            )
        )
        self.addParameter(QgsProcessingParameterBoolean("DOUBLE", self.tr("Double grid"), False))
        self.addParameter(_number("MARGIN", self.tr("Grow area by (m)"), 0, 0, 500))
        self._output_params()

    def _heading(self, parameters: dict, context: Any) -> float | None:
        if parameters.get("ANGLE") in (None, NULL, ""):
            return None
        return self.parameterAsDouble(parameters, "ANGLE", context)

    def processAlgorithm(self, parameters: dict, context: Any, feedback: Any) -> dict:  # noqa: N802
        drone, camera = self._drone(parameters, context)
        source = self.parameterAsSource(parameters, "INPUT", context)
        if source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, "INPUT"))
        area = self._plan(polygons_from_rings, _polygons(source, context))
        params = self._survey_params_value(
            parameters,
            context,
            heading_deg=self._heading(parameters, context),
            double=self.parameterAsBoolean(parameters, "DOUBLE", context),
            margin_m=self.parameterAsDouble(parameters, "MARGIN", context),
        )
        elevation, takeoff = self._terrain(parameters, context)
        mission = self._plan(plan_survey, area, drone, camera, params, elevation, takeoff)
        return self._emit(mission, parameters, context, feedback)


class CorridorAlgorithm(_Base):
    def name(self) -> str:
        return "corridor"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("Corridor")

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "Parallel passes along a line (road, railway, river): one on the axis plus pairs on "
            "both sides. The number of passes must be odd."
        )

    def initAlgorithm(self, config: Any = None) -> None:  # noqa: N802
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                "INPUT", self.tr("Corridor axis"), _source_types("TypeVectorLine")
            )
        )
        self._drone_params()
        self._survey_params()
        self.addParameter(
            _number("LINES", self.tr("Number of passes (odd)"), 3, 1, 15, integer=True)
        )
        self._output_params()

    def processAlgorithm(self, parameters: dict, context: Any, feedback: Any) -> dict:  # noqa: N802
        drone, camera = self._drone(parameters, context)
        source = self.parameterAsSource(parameters, "INPUT", context)
        if source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, "INPUT"))
        axis = self._plan(first_line, _lines(source, context))
        params = self._survey_params_value(parameters, context)
        elevation, takeoff = self._terrain(parameters, context)
        lines = self.parameterAsInt(parameters, "LINES", context)
        mission = self._plan(plan_corridor, axis, drone, camera, params, lines, elevation, takeoff)
        return self._emit(mission, parameters, context, feedback)


class OrbitAlgorithm(_Base):
    def name(self) -> str:
        return "orbit"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("Orbit")

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "Circle around a point of interest with the camera locked on it. Heights are "
            "relative to the takeoff point."
        )

    def initAlgorithm(self, config: Any = None) -> None:  # noqa: N802
        self._drone_params()
        self.addParameter(QgsProcessingParameterPoint("CENTER", self.tr("Center of the orbit")))
        self.addParameter(_number("RADIUS", self.tr("Radius (m)"), 40, 5, 500))
        self.addParameter(_number("HEIGHT", self.tr("Height above takeoff (m)"), 40, 5, 500))
        self.addParameter(_number("POINTS", self.tr("Waypoints on the circle"), 12, 3, 360, True))
        self.addParameter(
            _number(
                "TARGET_HEIGHT", self.tr("Height of the target above takeoff (m)"), 0, -100, 500
            )
        )
        self.addParameter(_number("SPEED", self.tr("Speed (m/s)"), 3, 0.5, 16))
        self.addParameter(
            QgsProcessingParameterBoolean("PHOTO_EACH", self.tr("Photo at each waypoint"), False)
        )
        self._output_params()

    def processAlgorithm(self, parameters: dict, context: Any, feedback: Any) -> dict:  # noqa: N802
        drone, _ = self._drone(parameters, context)
        mission = self._plan(
            plan_orbit,
            drone,
            self._lonlat(parameters, "CENTER", context),
            self.parameterAsDouble(parameters, "RADIUS", context),
            self.parameterAsDouble(parameters, "HEIGHT", context),
            self.parameterAsInt(parameters, "POINTS", context),
            self.parameterAsDouble(parameters, "TARGET_HEIGHT", context),
            self.parameterAsDouble(parameters, "SPEED", context),
            self.parameterAsBoolean(parameters, "PHOTO_EACH", context),
        )
        return self._emit(mission, parameters, context, feedback)


class FacadeAlgorithm(_Base):
    def name(self) -> str:
        return "facade"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("Facade (experimental)")

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "Vertical grid in front of a wall running from point A to point B. The drone stands "
            "away from the wall on the chosen side of A to B, shoots a photo at every waypoint, "
            "and heights are relative to takeoff (take off at wall-base level)."
        )

    def initAlgorithm(self, config: Any = None) -> None:  # noqa: N802
        self._drone_params()
        self.addParameter(QgsProcessingParameterPoint("BASE_A", self.tr("Wall base, point A")))
        self.addParameter(QgsProcessingParameterPoint("BASE_B", self.tr("Wall base, point B")))
        self.addParameter(_number("WALL_HEIGHT", self.tr("Wall height (m)"), 20, 2, 300))
        self.addParameter(_number("STANDOFF", self.tr("Distance from the wall (m)"), 15, 3, 100))
        self.addParameter(_number("FRONT", self.tr("Vertical overlap (%)"), 75, 10, 95))
        self.addParameter(_number("SIDE", self.tr("Horizontal overlap (%)"), 70, 10, 95))
        self.addParameter(
            QgsProcessingParameterEnum(
                "WALL_SIDE",
                self.tr("Drone side, looking from A to B"),
                [self.tr("Left"), self.tr("Right")],
                defaultValue=0,
            )
        )
        self.addParameter(_number("SPEED", self.tr("Speed (m/s)"), 1.5, 0.5, 16))
        self._output_params()

    def processAlgorithm(self, parameters: dict, context: Any, feedback: Any) -> dict:  # noqa: N802
        drone, camera = self._drone(parameters, context)
        side = ("left", "right")[self.parameterAsEnum(parameters, "WALL_SIDE", context)]
        mission = self._plan(
            plan_facade,
            drone,
            camera,
            self._lonlat(parameters, "BASE_A", context),
            self._lonlat(parameters, "BASE_B", context),
            self.parameterAsDouble(parameters, "WALL_HEIGHT", context),
            self.parameterAsDouble(parameters, "STANDOFF", context),
            self.parameterAsDouble(parameters, "FRONT", context) / 100,
            self.parameterAsDouble(parameters, "SIDE", context) / 100,
            side,
            self.parameterAsDouble(parameters, "SPEED", context),
        )
        return self._emit(mission, parameters, context, feedback)


ALGORITHMS = [SurveyGridAlgorithm, CorridorAlgorithm, OrbitAlgorithm, FacadeAlgorithm]
