import { useRef, useState } from "react";

import { importFile } from "../api/client";
import { modeInfo, pickImported } from "../api/geometry";
import { useStore } from "../store";
import { presetFor } from "./presets";

const WHAT = { polygon: "a área", path: "o trajeto", point: "o ponto central" } as const;

export function AreaStep() {
  const mode = useStore((s) => s.mode);
  const points = useStore((s) => s.points.length);
  const { undoPoint, clearPoints, importPoints } = useStore.getState();
  const fileInput = useRef<HTMLInputElement>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const { min, max, shape } = modeInfo(mode);
  const canImport = shape !== "point";

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    setImportError(null);
    try {
      const picked = pickImported(mode, await importFile(file));
      if (picked) importPoints(picked);
      else setImportError(`O arquivo não tem ${WHAT[shape]} para ${presetFor(mode).title}.`);
    } catch (err) {
      setImportError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <>
      <h2 className="section-title">Marque {WHAT[shape]} no mapa</h2>
      <p className="lead">
        Clique no mapa para adicionar pontos. Arraste um pino para movê-lo; clique com o botão
        direito (ou segure no celular) para removê-lo.
      </p>
      <p className="counter" aria-live="polite">
        {points} {points === 1 ? "ponto" : "pontos"}
        {points < min && ` · faltam ${(min - points).toString()}`}
        {Number.isFinite(max) && ` · máximo ${max.toString()}`}
      </p>

      <div className="button-row">
        <button type="button" className="secondary" disabled={points === 0} onClick={undoPoint}>
          Desfazer último
        </button>
        <button type="button" className="secondary" disabled={points === 0} onClick={clearPoints}>
          Limpar
        </button>
      </div>

      {canImport && (
        <div className="import">
          <input
            ref={fileInput}
            type="file"
            hidden
            accept=".kml,.kmz,.geojson,.json"
            onChange={(e) => {
              void onFile(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
          <button type="button" className="secondary" onClick={() => fileInput.current?.click()}>
            Importar KML, KMZ ou GeoJSON
          </button>
          {importError && (
            <p role="alert" className="error-text">
              {importError}
            </p>
          )}
        </div>
      )}
    </>
  );
}
