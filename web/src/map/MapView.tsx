import "leaflet/dist/leaflet.css";

import { useMemo, useState } from "react";
import { MapContainer, TileLayer } from "react-leaflet";

import { modeInfo } from "../api/geometry";
import { ElevationProfile } from "../flight/ElevationProfile";
import { InfoCard } from "../flight/InfoCard";
import { Legend } from "../flight/Legend";
import { useStore } from "../store";
import { BASEMAPS, projectBasemap } from "./basemaps";
import {
  DrawnShape,
  FitOnImport,
  FitToPlan,
  FitToTask,
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
  const task = useStore((s) => s.task);
  const basemaps = useMemo(
    () =>
      task?.assets.orthophoto ? [projectBasemap(task.tiles, task.extent), ...BASEMAPS] : BASEMAPS,
    [task],
  );
  const [chosen, setBasemapId] = useState<string | null>(null); // null: the default
  const basemap = basemaps.find((b) => b.id === chosen) ?? basemaps[0];
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
        {basemap?.layers.map((layer) => (
          <TileLayer key={layer.url} {...layer} />
        ))}
        <MapClicks />
        <DrawnShape />
        <PlannedRoute />
        <TakeoffMarker />
        <FitToTask />
        <FitToPlan />
        <FitOnImport />
        <LocateOnStart />
      </MapContainer>

      <div className="basemaps" role="group" aria-label="Mapa de fundo">
        {basemaps.map((b) => (
          <button
            key={b.id}
            type="button"
            aria-pressed={b.id === basemap?.id}
            onClick={() => {
              setBasemapId(b.id);
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
