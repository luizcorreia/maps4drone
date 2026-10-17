import { describe, expect, it } from "vitest";

import type { PlanResult } from "../api/types";
import { boundsOf, routePath, toLatLng, waypointPoints } from "./geo";

const plan = {
  geojson: {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: { kind: "route" },
        geometry: {
          type: "LineString",
          coordinates: [
            [-51.9, -23.15],
            [-51.8, -23.1],
          ],
        },
      },
      {
        type: "Feature",
        properties: { kind: "waypoint", index: 0, height: 80 },
        geometry: { type: "Point", coordinates: [-51.9, -23.15] },
      },
    ],
  },
} as PlanResult;

describe("geo", () => {
  it("swaps GeoJSON order to Leaflet order", () => {
    expect(toLatLng([-51.9, -23.15])).toEqual([-23.15, -51.9]);
  });

  it("extracts the route and the waypoints from a plan", () => {
    expect(routePath(plan)).toEqual([
      [-23.15, -51.9],
      [-23.1, -51.8],
    ]);
    expect(waypointPoints(plan)).toEqual([{ index: 0, position: [-23.15, -51.9], height: 80 }]);
  });

  it("returns no route for an empty plan", () => {
    const empty = {
      geojson: { type: "FeatureCollection", features: [] },
    } as unknown as PlanResult;
    expect(routePath(empty)).toEqual([]);
  });

  it("computes bounds, or null without points", () => {
    expect(
      boundsOf([
        [1, 5],
        [3, 2],
        [2, 9],
      ]),
    ).toEqual([
      [1, 2],
      [3, 9],
    ]);
    expect(boundsOf([])).toBeNull();
  });
});
