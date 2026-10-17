import { describe, expect, it } from "vitest";

import { pickImported, pointsFromGeometry, toGeometry } from "./geometry";
import type { Geometry, LngLat } from "./types";

const P: LngLat[] = [
  [0, 0],
  [1, 0],
  [1, 1],
];

describe("toGeometry", () => {
  it("closes the polygon ring", () => {
    expect(toGeometry("grid", P)).toEqual({
      type: "Polygon",
      coordinates: [[...P, P[0]]],
    });
  });

  it("needs the mode's minimum number of points", () => {
    expect(toGeometry("grid", P.slice(0, 2))).toBeNull();
    expect(toGeometry("corridor", P.slice(0, 1))).toBeNull();
    expect(toGeometry("orbit", [])).toBeNull();
  });

  it("uses only what the mode accepts", () => {
    expect(toGeometry("orbit", P)).toEqual({
      type: "Point",
      coordinates: P[0],
    });
    expect(toGeometry("facade", P)).toEqual({
      type: "LineString",
      coordinates: P.slice(0, 2),
    });
  });

  it("maps waypoints and corridors to the right GeoJSON types", () => {
    expect(toGeometry("waypoints", P)?.type).toBe("MultiPoint");
    expect(toGeometry("corridor", P)?.type).toBe("LineString");
  });
});

describe("pointsFromGeometry", () => {
  it("drops the closing vertex of a ring", () => {
    const polygon = toGeometry("grid", P);
    expect(polygon && pointsFromGeometry(polygon)).toEqual(P);
  });

  it("returns line and point coordinates as they are", () => {
    expect(pointsFromGeometry({ type: "LineString", coordinates: P })).toEqual(P);
    expect(pointsFromGeometry({ type: "Point", coordinates: [3, 4] })).toEqual([[3, 4]]);
  });
});

describe("pickImported", () => {
  const polygon = toGeometry("grid", P) as Extract<Geometry, { type: "Polygon" }>;
  const line: Extract<Geometry, { type: "LineString" }> = { type: "LineString", coordinates: P };

  it("takes the polygon for area modes and ignores a lone line", () => {
    expect(pickImported("grid", { polygon, line })).toEqual(P);
    expect(pickImported("double_grid", { polygon: null, line })).toBeNull();
  });

  it("prefers the line for path modes and falls back to the polygon outline", () => {
    expect(pickImported("corridor", { polygon, line })).toEqual(P);
    expect(pickImported("corridor", { polygon, line: null })).toEqual(P);
    expect(pickImported("facade", { polygon: null, line })).toEqual(P.slice(0, 2));
  });

  it("does not import into an orbit", () => {
    expect(pickImported("orbit", { polygon, line })).toBeNull();
  });
});
