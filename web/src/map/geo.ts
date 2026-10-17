import type { LngLat, PlanResult } from "../api/types";

/** [lat, lng], the order Leaflet uses. */
export type LatLng = [number, number];

export const toLatLng = ([lng, lat]: LngLat): LatLng => [lat, lng];

export function routePath(plan: PlanResult): LatLng[] {
  const route = plan.geojson.features.find((f) => f.geometry.type === "LineString");
  return route?.geometry.type === "LineString" ? route.geometry.coordinates.map(toLatLng) : [];
}

export interface WaypointPoint {
  index: number;
  position: LatLng;
  height: number;
}

export function waypointPoints(plan: PlanResult): WaypointPoint[] {
  return plan.geojson.features.flatMap((f) =>
    f.properties.kind === "waypoint" && f.geometry.type === "Point"
      ? [
          {
            index: f.properties.index,
            position: toLatLng(f.geometry.coordinates),
            height: f.properties.height,
          },
        ]
      : [],
  );
}

export function boundsOf(points: readonly LatLng[]): [LatLng, LatLng] | null {
  if (points.length === 0) return null;
  const lats = points.map((p) => p[0]);
  const lngs = points.map((p) => p[1]);
  return [
    [Math.min(...lats), Math.min(...lngs)],
    [Math.max(...lats), Math.max(...lngs)],
  ];
}
