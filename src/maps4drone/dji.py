"""Writer for DJI Fly waypoint missions (WPML inside a KMZ).

Photos are taken at waypoints (reachPoint trigger), so the route is densified at the shot
distance for survey-style missions. The file layout and the drone/payload enums follow
what the DJI Fly app accepts for the consumer line; none of it is validated against a
real aircraft here, so check the mission in DJI Fly before flying.

DJI Fly caps the waypoints per mission, so long routes are split into several KMZ files
that share one waypoint at the seam.
"""

import dataclasses
import io
import math
import time
import zipfile

from .geo import Projector, wrap_180
from .model import Mission, Waypoint

MAX_WAYPOINTS = 195
TRANSIT_SPEED_MS = 12.0
GIMBAL_SETTLE_S = 2.5
_NS = 'xmlns="http://www.opengis.net/kml/2.2" xmlns:wpml="http://www.dji.com/wpmz/1.0.6"'


def photo_waypoints(mission: Mission) -> list[Waypoint]:
    """Waypoints that take a photo: legs are densified at the shot distance when the
    mission is interval-based (survey, corridor); otherwise the PHOTO waypoints stay."""
    wps = mission.waypoints
    if mission.shoot_interval_s is None:
        return [dataclasses.replace(w, action="PHOTO") if w.action == "PHOTO" else w for w in wps]
    shot = mission.speed_ms * mission.shoot_interval_s
    proj = Projector(wps[0].lng, wps[0].lat)
    xy = [proj.forward(w.lng, w.lat) for w in wps]
    out: list[Waypoint] = []
    for i, (a, b) in enumerate(zip(wps, wps[1:], strict=False)):
        n = max(1, math.ceil(math.dist(xy[i], xy[i + 1]) / shot))
        for k in range(n):
            t = k / n
            lng, lat = proj.inverse(
                xy[i][0] + (xy[i + 1][0] - xy[i][0]) * t,
                xy[i][1] + (xy[i + 1][1] - xy[i][1]) * t,
            )
            out.append(
                dataclasses.replace(
                    a, lat=lat, lng=lng, height=a.height + (b.height - a.height) * t, action="PHOTO"
                )
            )
    out.append(dataclasses.replace(wps[-1], action="PHOTO"))
    return out


def split_with_overlap(wps: list[Waypoint], limit: int = MAX_WAYPOINTS) -> list[list[Waypoint]]:
    """Chunks of at most `limit` waypoints; each chunk starts at the previous chunk's last."""
    if len(wps) <= limit:
        return [wps]
    chunks, start = [], 0
    while True:
        end = min(start + limit, len(wps))
        chunks.append(wps[start:end])
        if end == len(wps):
            return chunks
        start = end - 1


def _gimbal(pitch: float) -> str:
    return (
        "<wpml:actionActuatorFunc>gimbalRotate</wpml:actionActuatorFunc>"
        "<wpml:actionActuatorFuncParam><wpml:gimbalHeadingYawBase>aircraft</wpml:gimbalHeadingYawBase>"
        "<wpml:gimbalRotateMode>absoluteAngle</wpml:gimbalRotateMode>"
        "<wpml:gimbalPitchRotateEnable>1</wpml:gimbalPitchRotateEnable>"
        f"<wpml:gimbalPitchRotateAngle>{pitch:g}</wpml:gimbalPitchRotateAngle>"
        "<wpml:gimbalRollRotateEnable>0</wpml:gimbalRollRotateEnable>"
        "<wpml:gimbalRollRotateAngle>0</wpml:gimbalRollRotateAngle>"
        "<wpml:gimbalYawRotateEnable>0</wpml:gimbalYawRotateEnable>"
        "<wpml:gimbalYawRotateAngle>0</wpml:gimbalYawRotateAngle>"
        "<wpml:payloadPositionIndex>0</wpml:payloadPositionIndex></wpml:actionActuatorFuncParam>"
    )


def _hover(seconds: float) -> str:
    return (
        "<wpml:actionActuatorFunc>hover</wpml:actionActuatorFunc><wpml:actionActuatorFuncParam>"
        f"<wpml:hoverTime>{seconds:g}</wpml:hoverTime></wpml:actionActuatorFuncParam>"
    )


_TAKE_PHOTO = (
    "<wpml:actionActuatorFunc>takePhoto</wpml:actionActuatorFunc><wpml:actionActuatorFuncParam>"
    "<wpml:payloadPositionIndex>0</wpml:payloadPositionIndex></wpml:actionActuatorFuncParam>"
)


def _heading(w: Waypoint) -> str:
    if w.yaw is None:
        mode, angle = "followWayline", 0
    else:
        mode, angle = "smoothTransition", round(wrap_180(w.yaw))
    return (
        f"<wpml:waypointHeadingParam><wpml:waypointHeadingMode>{mode}</wpml:waypointHeadingMode>"
        f"<wpml:waypointHeadingAngle>{angle}</wpml:waypointHeadingAngle></wpml:waypointHeadingParam>"
    )


def _placemark(i: int, w: Waypoint, speed: float, previous_pitch: float | None) -> str:
    actions = []
    if w.gimbal_pitch != previous_pitch:
        actions += [_gimbal(w.gimbal_pitch)]
        if previous_pitch is None:
            actions.append(_hover(GIMBAL_SETTLE_S))
    if w.hover_time:
        actions.append(_hover(w.hover_time))
    if w.action == "PHOTO":
        actions.append(_TAKE_PHOTO)
    group = ""
    if actions:
        body = "".join(
            f"<wpml:action><wpml:actionId>{n}</wpml:actionId>{a}</wpml:action>"
            for n, a in enumerate(actions)
        )
        group = (
            f"<wpml:actionGroup><wpml:actionGroupId>{i}</wpml:actionGroupId>"
            f"<wpml:actionGroupStartIndex>{i}</wpml:actionGroupStartIndex>"
            f"<wpml:actionGroupEndIndex>{i}</wpml:actionGroupEndIndex>"
            "<wpml:actionGroupMode>sequence</wpml:actionGroupMode>"
            "<wpml:actionTrigger><wpml:actionTriggerType>reachPoint</wpml:actionTriggerType>"
            f"</wpml:actionTrigger>{body}</wpml:actionGroup>"
        )
    return (
        f"<Placemark><wpml:index>{i}</wpml:index>"
        f"<Point><coordinates>{w.lng:.8f},{w.lat:.8f},0</coordinates></Point>"
        f"<wpml:executeHeight>{w.height:.2f}</wpml:executeHeight>"
        f"<wpml:waypointSpeed>{w.speed if w.speed is not None else speed:g}</wpml:waypointSpeed>"
        f"{_heading(w)}"
        "<wpml:waypointTurnParam><wpml:waypointTurnMode>coordinateTurn</wpml:waypointTurnMode>"
        "<wpml:waypointTurnDampingDist>0.2</wpml:waypointTurnDampingDist></wpml:waypointTurnParam>"
        f"{group}</Placemark>"
    )


def _mission_config(mission: Mission, takeoff_height: float, with_payload: bool) -> str:
    assert mission.drone.dji_enums is not None
    drone_enum, payload_enum = mission.drone.dji_enums
    payload = (
        f"<wpml:payloadInfo><wpml:payloadEnumValue>{payload_enum}</wpml:payloadEnumValue>"
        "<wpml:payloadSubEnumValue>0</wpml:payloadSubEnumValue>"
        "<wpml:payloadPositionIndex>0</wpml:payloadPositionIndex></wpml:payloadInfo>"
        if with_payload
        else ""
    )
    return (
        "<wpml:missionConfig><wpml:flyToWaylineMode>safely</wpml:flyToWaylineMode>"
        "<wpml:finishAction>goHome</wpml:finishAction>"
        "<wpml:exitOnRCLost>executeLostAction</wpml:exitOnRCLost>"
        "<wpml:executeRCLostAction>goBack</wpml:executeRCLostAction>"
        f"<wpml:takeOffSecurityHeight>{takeoff_height:g}</wpml:takeOffSecurityHeight>"
        f"<wpml:globalTransitionalSpeed>{min(TRANSIT_SPEED_MS, mission.drone.max_speed_ms):g}"
        "</wpml:globalTransitionalSpeed>"
        f"<wpml:droneInfo><wpml:droneEnumValue>{drone_enum}</wpml:droneEnumValue>"
        f"<wpml:droneSubEnumValue>0</wpml:droneSubEnumValue></wpml:droneInfo>{payload}"
        "</wpml:missionConfig>"
    )


def waylines_wpml(mission: Mission, wps: list[Waypoint]) -> str:
    pitches = [None, *(w.gimbal_pitch for w in wps)]
    placemarks = "".join(_placemark(i, w, mission.speed_ms, pitches[i]) for i, w in enumerate(wps))
    takeoff = max(20.0, round(max(w.height for w in wps)))
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><kml {_NS}><Document>'
        f"{_mission_config(mission, takeoff, with_payload=True)}"
        "<Folder><wpml:templateId>0</wpml:templateId>"
        "<wpml:executeHeightMode>relativeToStartPoint</wpml:executeHeightMode>"
        f"<wpml:waylineId>0</wpml:waylineId><wpml:autoFlightSpeed>{mission.speed_ms:g}"
        f"</wpml:autoFlightSpeed>{placemarks}</Folder></Document></kml>"
    )


def template_kml(mission: Mission, wps: list[Waypoint], created_ms: int) -> str:
    height = max(20.0, round(max(w.height for w in wps)))
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><kml {_NS}><Document>'
        f"<wpml:author>maps4drone</wpml:author><wpml:createTime>{created_ms}</wpml:createTime>"
        f"<wpml:updateTime>{created_ms}</wpml:updateTime>"
        f"{_mission_config(mission, height, with_payload=False)}"
        "<Folder><wpml:templateType>waypoint</wpml:templateType><wpml:templateId>0</wpml:templateId>"
        f"<wpml:globalHeight>{height:g}</wpml:globalHeight>"
        "<wpml:executeHeightMode>relativeToStartPoint</wpml:executeHeightMode>"
        "<wpml:waylineCoordinateSysParam><wpml:coordinateMode>WGS84</wpml:coordinateMode>"
        "<wpml:heightMode>relativeToStartPoint</wpml:heightMode></wpml:waylineCoordinateSysParam>"
        f"<wpml:autoFlightSpeed>{mission.speed_ms:g}</wpml:autoFlightSpeed>"
        "<wpml:gimbalPitchMode>manual</wpml:gimbalPitchMode>"
        "<wpml:globalWaypointTurnMode>coordinateTurn</wpml:globalWaypointTurnMode>"
        "<wpml:globalUseStraightLine>1</wpml:globalUseStraightLine>"
        "</Folder></Document></kml>"
    )


def mission_kmz(mission: Mission) -> list[bytes]:
    """One KMZ per flight (see MAX_WAYPOINTS)."""
    if mission.drone.dji_enums is None:
        raise ValueError(f"{mission.drone.name} has no DJI enum values")
    if not 0 < mission.speed_ms <= mission.drone.max_speed_ms:
        raise ValueError(f"speed must be in (0, {mission.drone.max_speed_ms}] m/s")
    wps = photo_waypoints(mission)
    if len(wps) < 2:
        raise ValueError("a DJI mission needs at least 2 waypoints")
    now = int(time.time() * 1000)
    files = []
    for chunk in split_with_overlap(wps):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("wpmz/template.kml", template_kml(mission, chunk, now))
            z.writestr("wpmz/waylines.wpml", waylines_wpml(mission, chunk))
        files.append(buf.getvalue())
    return files
