import { useState } from "react";

import { insideWebodm } from "../api/client";
import { modeInfo } from "../api/geometry";
import { useStore } from "../store";
import { AreaStep } from "./AreaStep";
import { MissionStep } from "./MissionStep";
import { PlanBar } from "./PlanBar";
import { ReviewStep } from "./ReviewStep";
import { SettingsStep } from "./SettingsStep";

const STEPS = [
  { id: "mission", label: "Missão", View: MissionStep },
  { id: "area", label: "Área", View: AreaStep },
  { id: "settings", label: "Ajustes", View: SettingsStep },
  { id: "review", label: "Revisar", View: ReviewStep },
] as const;

export function Panel() {
  const [index, setIndex] = useState(0);
  const mode = useStore((s) => s.mode);
  const points = useStore((s) => s.points.length);
  const status = useStore((s) => s.status);
  const hasProject = useStore((s) => s.projectId !== null);

  const current = STEPS[index] ?? STEPS[0];
  const needsArea = points < modeInfo(mode).min;
  const next = STEPS[index + 1];
  const blocked = current.id === "area" && needsArea;

  return (
    <aside className="panel" aria-label="Planejamento">
      {insideWebodm() && hasProject && <PlanBar />}
      <ol className="stepper">
        {STEPS.map((step, i) => (
          <li key={step.id}>
            <button
              type="button"
              aria-current={i === index ? "step" : undefined}
              disabled={i > 1 && needsArea}
              onClick={() => {
                setIndex(i);
              }}
            >
              <span className="step-n">{i + 1}</span>
              {step.label}
            </button>
          </li>
        ))}
      </ol>

      <div className="panel-body">
        <current.View />
      </div>

      <footer className="panel-footer">
        {status === "planning" && <span className="muted">Planejando…</span>}
        <button
          type="button"
          className="secondary"
          disabled={index === 0}
          onClick={() => {
            setIndex(index - 1);
          }}
        >
          Voltar
        </button>
        {next && (
          <button
            type="button"
            className="primary"
            disabled={blocked}
            title={blocked ? "Marque a área no mapa primeiro" : undefined}
            onClick={() => {
              setIndex(index + 1);
            }}
          >
            Próximo
          </button>
        )}
      </footer>
    </aside>
  );
}
