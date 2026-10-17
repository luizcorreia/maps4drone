import type { Camera, Mode, Params, PlanResult } from "../api/types";
import { routePath, waypointPoints, type LatLng } from "../map/geo";

/** Typical bright-day exposure, and the smear (in pixels) we accept before warning. */
export const EXPOSURE_S = 1 / 500;
export const BLUR_BUDGET_PX = 0.7;
/** Rough JPEG size per megapixel; real files vary with the scene. */
export const MB_PER_MEGAPIXEL = 0.5;

const EARTH_RADIUS_M = 6_371_000;
const RAD = Math.PI / 180;

/** Distance in metres from the camera to what it photographs, per mode. */
export function subjectDistance(mode: Mode, p: Params): number {
  if (mode === "facade") return p.standoff;
  if (mode === "orbit") return Math.hypot(p.radius, Math.max(0, p.altitude - p.target_height));
  return p.altitude;
}

/** Ground sample distance in metres per pixel. */
export function gsdM(camera: Camera, distanceM: number): number {
  return (camera.sensor_w_mm * distanceM) / (camera.focal_mm * camera.image_w);
}

/** Ground (width, height) of one frame, landscape. */
export function footprintM(camera: Camera, distanceM: number): [number, number] {
  return [
    (camera.sensor_w_mm * distanceM) / camera.focal_mm,
    (camera.sensor_h_mm * distanceM) / camera.focal_mm,
  ];
}

export const lineSpacingM = (camera: Camera, distanceM: number, sidePct: number) =>
  footprintM(camera, distanceM)[0] * (1 - sidePct / 100);

export const shotDistanceM = (camera: Camera, distanceM: number, frontPct: number) =>
  footprintM(camera, distanceM)[1] * (1 - frontPct / 100);

/** Fastest speed that keeps motion smear under the budget. */
export const blurSpeedLimit = (gsd: number) => (BLUR_BUDGET_PX * gsd) / EXPOSURE_S;

export const photoSizeMb = (camera: Camera) =>
  ((camera.image_w * camera.image_h) / 1e6) * MB_PER_MEGAPIXEL;

export function formatStorage(mb: number): string {
  return mb >= 1000 ? `${(mb / 1000).toFixed(1)} GB` : `${Math.round(mb).toString()} MB`;
}

export function formatDuration(seconds: number): string {
  const total = Math.round(seconds);
  const m = Math.floor(total / 60);
  return `${m.toString()} min ${(total % 60).toString().padStart(2, "0")} s`;
}

export function haversineM([lat1, lng1]: LatLng, [lat2, lng2]: LatLng): number {
  const dLat = (lat2 - lat1) * RAD;
  const dLng = (lng2 - lng1) * RAD;
  const a =
    Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * RAD) * Math.cos(lat2 * RAD) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(a)));
}

export interface ProfilePoint {
  /** Metres flown along the route. */
  distance: number;
  /** Drone height relative to the takeoff point. */
  drone: number;
  /** Ground height relative to the takeoff point. */
  ground: number;
}

/**
 * Terrain and drone height along the route. Only meaningful when terrain following is on:
 * then every height is altitude + (ground - takeoff ground), so ground = height - altitude.
 */
export function elevationProfile(plan: PlanResult, altitude: number): ProfilePoint[] {
  const heights = new Map(waypointPoints(plan).map((w) => [w.index, w.height]));
  let distance = 0;
  let previous: LatLng | undefined;
  return routePath(plan).flatMap((position, index) => {
    const drone = heights.get(index);
    if (previous) distance += haversineM(previous, position);
    previous = position;
    return drone === undefined ? [] : [{ distance, drone, ground: drone - altitude }];
  });
}

export interface Advice {
  level: "warn" | "error";
  text: string;
}

/** Warnings the planner cannot know: the speed against the optics. */
export function blurAdvice(plan: PlanResult, camera: Camera, distanceM: number): Advice | null {
  const limit = blurSpeedLimit(gsdM(camera, distanceM));
  if (plan.speed <= limit) return null;
  return {
    level: "warn",
    text: `${plan.speed.toFixed(1)} m/s passa de ${limit.toFixed(1)} m/s: a imagem pode borrar (mais de ${BLUR_BUDGET_PX.toString()} px a 1/500 s). Voe mais alto ou use uma câmera com resolução maior.`,
  };
}
