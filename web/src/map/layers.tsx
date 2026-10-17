import L from "leaflet";
import { useEffect, useRef } from "react";
import {
  Circle,
  CircleMarker,
  Marker,
  Polygon,
  Polyline,
  Tooltip,
  useMap,
  useMapEvents,
} from "react-leaflet";

import { modeInfo } from "../api/geometry";
import type { LngLat } from "../api/types";
import { useStore } from "../store";
import { boundsOf, routePath, toLatLng, waypointPoints } from "./geo";

const SHAPE_STYLE = {
  color: "#58a6ff",
  weight: 2,
  dashArray: "6 6",
  fillOpacity: 0.08,
};
const ROUTE_STYLE = { color: "#3fb950", weight: 3 };

function pointIcon(label: string, className: string): L.DivIcon {
  return L.divIcon({
    className: `pin ${className}`,
    html: `<span>${label}</span>`,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  });
}

const toLngLat = (ll: L.LatLng): LngLat => [ll.lng, ll.lat];

/** Clicks draw points, or set the takeoff point while that is being picked. */
export function MapClicks() {
  const { addPoint, setParam, setPickingTakeoff } = useStore.getState();
  useMapEvents({
    click(e) {
      if (useStore.getState().pickingTakeoff) {
        setParam("takeoff", toLngLat(e.latlng));
        setPickingTakeoff(false);
      } else {
        addPoint(toLngLat(e.latlng));
      }
    },
  });
  return null;
}

/** What the user drew: draggable numbered pins, plus the outline they describe. */
export function DrawnShape() {
  const mode = useStore((s) => s.mode);
  const points = useStore((s) => s.points);
  const radius = useStore((s) => s.params.radius);
  const movePoint = useStore((s) => s.movePoint);
  const removePoint = useStore((s) => s.removePoint);
  const latlngs = points.map(toLatLng);
  const { shape } = modeInfo(mode);

  return (
    <>
      {shape === "polygon" && latlngs.length >= 3 && (
        <Polygon positions={latlngs} pathOptions={SHAPE_STYLE} />
      )}
      {shape === "path" && latlngs.length >= 2 && (
        <Polyline positions={latlngs} pathOptions={SHAPE_STYLE} />
      )}
      {mode === "orbit" && latlngs[0] && (
        <Circle center={latlngs[0]} radius={radius} pathOptions={SHAPE_STYLE} />
      )}
      {latlngs.map((position, i) => (
        <Marker
          key={i}
          position={position}
          draggable
          icon={pointIcon(String(i + 1), "pin-draw")}
          eventHandlers={{
            dragend: (e) => {
              movePoint(i, toLngLat((e.target as L.Marker).getLatLng()));
            },
            contextmenu: () => {
              removePoint(i);
            },
          }}
        />
      ))}
    </>
  );
}

const MAX_WAYPOINT_DOTS = 1500;

export function PlannedRoute() {
  const plan = useStore((s) => s.plan);
  if (!plan) return null;
  const path = routePath(plan);
  const waypoints = waypointPoints(plan);
  const first = path[0];
  const last = path[path.length - 1];
  return (
    <>
      <Polyline positions={path} pathOptions={ROUTE_STYLE} />
      {waypoints.length <= MAX_WAYPOINT_DOTS &&
        waypoints.map((w) => (
          <CircleMarker
            key={w.index}
            center={w.position}
            radius={3}
            pathOptions={{
              color: "#0d1117",
              weight: 1,
              fillColor: "#e6edf3",
              fillOpacity: 1,
            }}
          >
            <Tooltip>{`#${(w.index + 1).toString()} · ${w.height.toFixed(0)} m`}</Tooltip>
          </CircleMarker>
        ))}
      {first && <Marker position={first} icon={pointIcon("I", "pin-start")} interactive={false} />}
      {last && last !== first && (
        <Marker position={last} icon={pointIcon("F", "pin-end")} interactive={false} />
      )}
    </>
  );
}

export function TakeoffMarker() {
  const takeoff = useStore((s) => s.params.takeoff);
  const setParam = useStore((s) => s.setParam);
  if (!takeoff) return null;
  return (
    <Marker
      position={toLatLng(takeoff)}
      draggable
      icon={pointIcon("D", "pin-takeoff")}
      eventHandlers={{
        dragend: (e) => {
          setParam("takeoff", toLngLat((e.target as L.Marker).getLatLng()));
        },
      }}
    >
      <Tooltip>Decolagem</Tooltip>
    </Marker>
  );
}

/** Frames the route when a plan first appears after there was none. */
export function FitToPlan() {
  const map = useMap();
  const plan = useStore((s) => s.plan);
  const hadPlan = useRef(false);
  useEffect(() => {
    if (plan && !hadPlan.current) {
      const bounds = boundsOf(routePath(plan));
      if (bounds) map.fitBounds(bounds, { padding: [60, 60], maxZoom: 19 });
    }
    hadPlan.current = plan !== null;
  }, [plan, map]);
  return null;
}

/** Frames the drawn points when they arrive from an import. */
export function FitOnImport() {
  const map = useMap();
  const fitSignal = useStore((s) => s.fitSignal);
  useEffect(() => {
    if (fitSignal === 0) return;
    const bounds = boundsOf(useStore.getState().points.map(toLatLng));
    if (bounds) map.fitBounds(bounds, { padding: [60, 60], maxZoom: 19 });
  }, [fitSignal, map]);
  return null;
}

const LOCATE_TIMEOUT_MS = 5000;
const LOCATE_ZOOM = 16;

/** Starts on the user's position when the browser allows it; never blocks the map. */
export function LocateOnStart() {
  const map = useMap();
  useEffect(() => {
    if (!("geolocation" in navigator)) return;
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        if (useStore.getState().points.length === 0) {
          map.setView([coords.latitude, coords.longitude], LOCATE_ZOOM);
        }
      },
      () => undefined,
      { timeout: LOCATE_TIMEOUT_MS },
    );
  }, [map]);
  return null;
}
