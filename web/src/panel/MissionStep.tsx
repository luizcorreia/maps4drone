import { selectDrone, useStore } from "../store";
import { PRESETS } from "./presets";

export function MissionStep() {
  const drones = useStore((s) => s.drones);
  const drone = useStore(selectDrone);
  const mode = useStore((s) => s.mode);
  const setDrone = useStore((s) => s.setDrone);
  const applyPreset = useStore((s) => s.applyPreset);

  return (
    <>
      <div className="field">
        <label htmlFor="drone">Drone</label>
        <select
          id="drone"
          value={drone?.id ?? ""}
          disabled={drones.length === 0}
          onChange={(e) => {
            setDrone(e.target.value);
          }}
        >
          {drones.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
        {drone?.export_format === "dji" && (
          <p className="field-hint warn-text">
            Exportação DJI ainda não validada em voo: confira a missão no DJI Fly antes de decolar.
          </p>
        )}
      </div>

      <h2 className="section-title">Tipo de missão</h2>
      <div className="cards" role="radiogroup" aria-label="Tipo de missão">
        {PRESETS.map((preset) => (
          <button
            key={preset.mode}
            type="button"
            role="radio"
            aria-checked={preset.mode === mode}
            className="card"
            onClick={() => {
              applyPreset(preset.mode, preset.params);
            }}
          >
            <strong>{preset.title}</strong>
            <span>{preset.description}</span>
          </button>
        ))}
      </div>
    </>
  );
}
