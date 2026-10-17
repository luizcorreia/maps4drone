export interface TileSource {
  url: string;
  attribution: string;
  maxZoom: number;
  maxNativeZoom?: number;
}

export interface Basemap {
  id: "street" | "satellite" | "hybrid";
  label: string;
  /** Drawn in order, so labels go last. */
  layers: TileSource[];
}

const STREET: TileSource = {
  url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
  attribution: "© OpenStreetMap",
  maxZoom: 22,
  maxNativeZoom: 19,
};

const SATELLITE: TileSource = {
  url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  attribution: "Esri, Maxar, Earthstar Geographics",
  maxZoom: 22,
  // Past this level Esri serves "Map data not yet available" tiles for much of the world
  maxNativeZoom: 17,
};

const LABELS: TileSource = {
  url: "https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png",
  attribution: "© CARTO",
  maxZoom: 22,
  maxNativeZoom: 19,
};

export const BASEMAPS: readonly Basemap[] = [
  { id: "street", label: "Mapa", layers: [STREET] },
  { id: "satellite", label: "Satélite", layers: [SATELLITE] },
  { id: "hybrid", label: "Híbrido", layers: [SATELLITE, LABELS] },
];
