import "leaflet/dist/leaflet.css";

import { useState } from "react";
import { MapContainer, TileLayer } from "react-leaflet";

import { modeInfo } from "../api/geometry";
import { ElevationProfile } from "../flight/ElevationProfile";
import { InfoCard } from "../flight/InfoCard";
import { Legend } from "../flight/Legend";
import { useStore } from "../store";
import { BASEMAPS, type Basemap } from "./basemaps";
import {
  DrawnShape,
  FitOnImport,
  FitToPlan,
  LocateOnStart,
  MapClicks,
  PlannedRoute,
  TakeoffMarker,
} from "./layers";

const BRAZIL_CENTER: [number, number] = [-14.2, -51.9];

interface Hint {
  text: string;
  tone: "info" | "error";
}

function useHint(): Hint | null {
  const mode = useStore((s) => s.mode);
  const points = useStore((s) => s.points.length);
  const picking = useStore((s) => s.pickingTakeoff);
  const status = useStore((s) => s.status);
  const error = useStore((s) => s.error);
  if (picking) return { text: "Clique no mapa para marcar o ponto de decolagem", tone: "info" };
  const { min, shape } = modeInfo(mode);
  if (points < min) {
    const what = { polygon: "a área de voo", path: "o trajeto", point: "o centro da órbita" }[
      shape
    ];
    return {
      text: `Clique no mapa para marcar ${what} (${points.toString()}/${min.toString()} pontos)`,
      tone: "info",
    };
  }
  if (status === "error" && error) return { text: error, tone: "error" };
  if (status === "planning") return { text: "Planejando…", tone: "info" };
  return null;
}

export function MapView() {
  const [basemap, setBasemap] = useState<Basemap>(BASEMAPS[0] as Basemap);
  const picking = useStore((s) => s.pickingTakeoff);
  const hint = useHint();

  return (
    <div className={`map-wrap${picking ? " map-picking" : ""}`}>
      <MapContainer
        center={BRAZIL_CENTER}
        zoom={4}
        maxZoom={22}
        zoomControl={false}
        preferCanvas
        className="map"
      >
        {basemap.layers.map((layer) => (
          <TileLayer key={layer.url} {...layer} />
        ))}
        <MapClicks />
        <DrawnShape />
        <PlannedRoute />
        <TakeoffMarker />
        <FitToPlan />
        <FitOnImport />
        <LocateOnStart />
      </MapContainer>

      <div className="basemaps" role="group" aria-label="Mapa de fundo">
        {BASEMAPS.map((b) => (
          <button
            key={b.id}
            type="button"
            aria-pressed={b.id === basemap.id}
            onClick={() => {
              setBasemap(b);
            }}
          >
            {b.label}
          </button>
        ))}
      </div>

      <div className="map-cards">
        <InfoCard />
        <Legend />
      </div>

      <ElevationProfile />

      {hint && (
        <div className={`map-hint map-hint-${hint.tone}`} role="status">
          {hint.text}
        </div>
      )}
    </div>
  );
}
