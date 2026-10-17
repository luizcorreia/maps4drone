import type { Geometry, ImportResult, LngLat, Mode } from "./types";

export type Shape = "polygon" | "path" | "point";

export interface ModeInfo {
  id: Mode;
  label: string;
  /** What the user draws; switching between modes of the same shape keeps the points. */
  shape: Shape;
  /** Points needed before a plan can be requested. */
  min: number;
  /** The mode stops accepting points after this many. */
  max: number;
}

export const MODES: readonly ModeInfo[] = [
  { id: "grid", shape: "polygon", label: "Grid", min: 3, max: Infinity },
  {
    id: "double_grid",
    shape: "polygon",
    label: "Grid duplo",
    min: 3,
    max: Infinity,
  },
  { id: "corridor", shape: "path", label: "Corredor", min: 2, max: Infinity },
  { id: "facade", shape: "path", label: "Fachada", min: 2, max: 2 },
  { id: "orbit", shape: "point", label: "Órbita", min: 1, max: 1 },
  { id: "waypoints", shape: "path", label: "Waypoints", min: 2, max: Infinity },
];

export function modeInfo(mode: Mode): ModeInfo {
  const info = MODES.find((m) => m.id === mode);
  if (!info) throw new Error(`unknown mode ${mode}`);
  return info;
}

/** GeoJSON for what the user drew, or null while there are too few points. */
export function toGeometry(mode: Mode, points: readonly LngLat[]): Geometry | null {
  const { min, max } = modeInfo(mode);
  if (points.length < min) return null;
  const used = points.slice(0, max);
  const first = used[0];
  if (!first) return null;
  switch (mode) {
    case "grid":
    case "double_grid":
      return { type: "Polygon", coordinates: [[...used, first]] };
    case "orbit":
      return { type: "Point", coordinates: first };
    case "waypoints":
      return { type: "MultiPoint", coordinates: used };
    case "corridor":
    case "facade":
      return { type: "LineString", coordinates: used };
  }
}

/** Points of an imported shape, without the ring's repeated closing vertex. */
export function pointsFromGeometry(geometry: Geometry): LngLat[] {
  switch (geometry.type) {
    case "Point":
      return [geometry.coordinates];
    case "Polygon":
      return (geometry.coordinates[0] ?? []).slice(0, -1);
    default:
      return geometry.coordinates;
  }
}

/** The points to take from an imported file for this mode, or null when it has nothing usable. */
export function pickImported(mode: Mode, result: ImportResult): LngLat[] | null {
  const { shape, max } = modeInfo(mode);
  if (shape === "polygon") return result.polygon ? pointsFromGeometry(result.polygon) : null;
  if (shape === "path") {
    const source = result.line ?? result.polygon;
    return source ? pointsFromGeometry(source).slice(0, max) : null;
  }
  return null;
}
