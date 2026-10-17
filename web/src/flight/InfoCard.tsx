import { useState } from "react";

import { useStore, selectCamera, selectDrone } from "../store";
import {
  blurAdvice,
  blurSpeedLimit,
  formatDuration,
  formatStorage,
  gsdM,
  lineSpacingM,
  photoSizeMb,
  shotDistanceM,
  subjectDistance,
} from "./metrics";

function Item({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div className="info-item">
      <dt>{label}</dt>
      <dd>
        {value}
        {unit && <span className="unit"> {unit}</span>}
      </dd>
    </div>
  );
}

/** Numbers a pilot checks before flying; recomputed with every plan. */
export function InfoCard() {
  const [open, setOpen] = useState(true);
  const plan = useStore((s) => s.plan);
  const mode = useStore((s) => s.mode);
  const params = useStore((s) => s.params);
  const camera = useStore(selectCamera);
  const drone = useStore(selectDrone);
  if (!plan || !camera) return null;

  const distance = subjectDistance(mode, params);
  const gsd = gsdM(camera, distance);
  const surveyLike = mode === "grid" || mode === "double_grid" || mode === "corridor";
  const timed = plan.interval !== null;
  const photos = timed ? plan.stats.images[String(plan.interval)] : undefined;
  const blur = blurAdvice(plan, camera, distance);
  const { stats } = plan;

  return (
    <section className="info-card" aria-label="Dados do voo">
      <button
        type="button"
        className="info-toggle"
        aria-expanded={open}
        onClick={() => {
          setOpen(!open);
        }}
      >
        <span>Dados do voo</span>
        <span aria-hidden>{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <dl className="info-grid">
          <Item label="GSD" value={(gsd * 100).toFixed(2)} unit="cm/px" />
          {surveyLike && (
            <>
              <Item
                label="Espaço entre faixas"
                value={lineSpacingM(camera, distance, params.side).toFixed(1)}
                unit="m"
              />
              <Item
                label="Passo entre fotos"
                value={shotDistanceM(camera, distance, params.front).toFixed(1)}
                unit="m"
              />
            </>
          )}
          {photos !== undefined && (
            <>
              <Item label="Fotos" value={`~${photos.toString()}`} />
              <Item
                label="Armazenamento"
                value={`~${formatStorage(photos * photoSizeMb(camera))}`}
              />
            </>
          )}
          <Item label="Velocidade" value={plan.speed.toFixed(1)} unit="m/s" />
          <Item label="Máx. sem borrar" value={blurSpeedLimit(gsd).toFixed(1)} unit="m/s" />
          <Item label="Distância" value={(stats.distance_m / 1000).toFixed(2)} unit="km" />
          <Item
            label="Duração"
            value={`${formatDuration(stats.duration_s)} · ${stats.batteries.toString()} ${stats.batteries === 1 ? "bateria" : "baterias"}`}
          />
          {stats.area_ha !== null && (
            <Item label="Área" value={stats.area_ha.toFixed(2)} unit="ha" />
          )}
        </dl>
      )}
      {open && blur && (
        <p className="info-warn" role="note">
          {blur.text}
        </p>
      )}
      {open && drone && stats.batteries > 1 && (
        <p className="info-warn" role="note">
          Mais de uma bateria ({drone.flight_minutes.toString()} min de voo cada): planeje a troca.
        </p>
      )}
    </section>
  );
}
