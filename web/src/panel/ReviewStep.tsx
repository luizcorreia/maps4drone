import { useState } from "react";

import {
  blurAdvice,
  formatDuration,
  formatStorage,
  photoSizeMb,
  subjectDistance,
} from "../flight/metrics";
import { selectCamera, selectDrone, useStore } from "../store";
import { downloadFile } from "../ui/download";

export function ReviewStep() {
  const plan = useStore((s) => s.plan);
  const status = useStore((s) => s.status);
  const error = useStore((s) => s.error);
  const drone = useStore(selectDrone);
  const camera = useStore(selectCamera);
  const mode = useStore((s) => s.mode);
  const params = useStore((s) => s.params);
  const exportMission = useStore((s) => s.exportMission);
  const [busy, setBusy] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const onExport = async () => {
    setBusy(true);
    setExportError(null);
    try {
      downloadFile(await exportMission());
    } catch (err) {
      setExportError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  if (status === "error" && error) {
    return (
      <p role="alert" className="error-text">
        {error}
      </p>
    );
  }
  if (!plan) {
    return (
      <p className="lead">
        {status === "planning" ? "Planejando…" : "Marque a área para ver o resumo."}
      </p>
    );
  }

  const { stats } = plan;
  const photos = plan.interval === null ? undefined : stats.images[String(plan.interval)];
  const blur = camera && blurAdvice(plan, camera, subjectDistance(mode, params));
  const warnings = [...plan.warnings, ...(blur ? [blur.text] : [])];
  const isDji = drone?.export_format === "dji";

  return (
    <>
      <dl className="summary">
        <dt>Waypoints</dt>
        <dd>{stats.waypoints}</dd>
        <dt>Distância</dt>
        <dd>{(stats.distance_m / 1000).toFixed(2)} km</dd>
        <dt>Duração</dt>
        <dd>
          {formatDuration(stats.duration_s)} · {stats.batteries}{" "}
          {stats.batteries === 1 ? "bateria" : "baterias"}
        </dd>
        <dt>Velocidade</dt>
        <dd>{plan.speed.toFixed(1)} m/s</dd>
        {stats.area_ha !== null && (
          <>
            <dt>Área</dt>
            <dd>{stats.area_ha.toFixed(2)} ha</dd>
          </>
        )}
        {photos !== undefined && camera && (
          <>
            <dt>Fotos</dt>
            <dd>
              ~{photos} ({plan.interval} s) · ~{formatStorage(photos * photoSizeMb(camera))}
            </dd>
          </>
        )}
      </dl>

      {warnings.length > 0 && (
        <ul className="warnings" aria-label="Avisos">
          {warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}

      <button
        type="button"
        className="primary wide"
        disabled={busy}
        onClick={() => void onExport()}
      >
        {busy ? "Gerando…" : isDji ? "Baixar KMZ DJI" : "Baixar missão Atom 2"}
      </button>
      {exportError && (
        <p role="alert" className="error-text">
          {exportError}
        </p>
      )}

      <p className="field-hint">
        {isDji
          ? "Copie o KMZ para a pasta de waypoints do DJI Fly, substituindo uma missão existente, e confira a rota no app."
          : `Configure o temporizador da câmera para ${plan.interval?.toString() ?? "o intervalo indicado"} s. Substitua os arquivos da missão dummy criada no app Potensic Eve.`}
      </p>
    </>
  );
}
