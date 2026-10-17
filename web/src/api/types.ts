export type Mode = "waypoints" | "grid" | "double_grid" | "corridor" | "facade" | "orbit";

/** [lng, lat], the order GeoJSON and the API use. */
export type LngLat = [number, number];

export type ExportFormat = "atom2" | "dji";

export interface Camera {
  name: string;
  sensor_w_mm: number;
  sensor_h_mm: number;
  focal_mm: number;
  image_w: number;
  image_h: number;
  rolling_shutter_ms: number;
}

export interface Drone {
  id: string;
  name: string;
  cameras: Record<string, Camera>;
  default_camera: string;
  flight_minutes: number;
  max_speed_ms: number;
  max_height_m: number;
  shoot_intervals_s: number[];
  export_format: ExportFormat;
  dji_enums: [number, number] | null;
}

export interface Params {
  drone: string;
  camera: string | null;
  altitude: number;
  front: number;
  side: number;
  /** Compass bearing of the flight lines; null lets the planner follow the long axis. */
  angle: number | null;
  interval: number;
  pitch: number;
  margin: number;
  speed: number;
  terrain: boolean;
  takeoff: LngLat | null;
  terrain_step: number;
  lines: number;
  radius: number;
  points: number;
  target_height: number;
  photo_each: boolean;
  wall_height: number;
  standoff: number;
  wall_side: "left" | "right";
}

export type Geometry =
  | { type: "Point"; coordinates: LngLat }
  | { type: "MultiPoint"; coordinates: LngLat[] }
  | { type: "LineString"; coordinates: LngLat[] }
  | { type: "Polygon"; coordinates: LngLat[][] };

/** Where terrain heights come from when a WebODM task is open: its own models, or online. */
export type DemSource = "dsm" | "dtm" | "online";

export interface PlanRequest {
  mode: Mode;
  geometry: Geometry | null;
  params: Params;
  /** Only sent inside WebODM, for terrain following with a project's DSM or DTM. */
  dem?: { layer: "dsm" | "dtm" };
}

/** The WebODM task the page was opened for (?task=<id>). */
export interface TaskContext {
  id: string;
  project: number | string;
  name: string;
  /** [west, south, east, north] */
  extent: [number, number, number, number] | null;
  assets: { orthophoto: boolean; dsm: boolean; dtm: boolean };
  /** Leaflet tile URL template of the task's orthophoto. */
  tiles: string;
}

export interface PlanStats {
  waypoints: number;
  distance_m: number;
  duration_s: number;
  batteries: number;
  /** Photo count keyed by shooting interval in seconds. */
  images: Record<string, number>;
  area_ha: number | null;
}

export interface RouteFeature {
  type: "Feature";
  properties: { kind: "route" };
  geometry: { type: "LineString"; coordinates: LngLat[] };
}

export interface WaypointFeature {
  type: "Feature";
  properties: { kind: "waypoint"; index: number; height: number };
  geometry: { type: "Point"; coordinates: LngLat };
}

export interface PlanResult {
  geojson: {
    type: "FeatureCollection";
    features: (RouteFeature | WaypointFeature)[];
  };
  stats: PlanStats;
  warnings: string[];
  speed: number;
  interval: number | null;
}

export interface ImportResult {
  polygon: Extract<Geometry, { type: "Polygon" }> | null;
  line: Extract<Geometry, { type: "LineString" }> | null;
}

export interface MissionFile {
  blob: Blob;
  filename: string;
}
