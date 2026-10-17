import type { SavedPlan } from "../api/types";
import { selectDirty, selectRequest, useStore } from "../store";

const STATUS_LABEL: Record<SavedPlan["status"], string> = {
  planned: "planejado",
  flown: "realizado",
};

const DISCARD = "Descartar as alterações não salvas deste plano?";

/** The saved plans of the open WebODM project: name it, save it, reopen it later. */
export function PlanBar() {
  const plans = useStore((s) => s.plans);
  const planId = useStore((s) => s.planId);
  const planName = useStore((s) => s.planName);
  const busy = useStore((s) => s.plansBusy);
  const error = useStore((s) => s.plansError);
  const dirty = useStore(selectDirty);
  const canSave = useStore((s) => selectRequest(s) !== null) && planName.trim() !== "";
  const { setPlanName, savePlan, openPlan, newPlan, removePlan } = useStore.getState();

  const confirmDiscard = () => !dirty || window.confirm(DISCARD);

  return (
    <section className="plan-bar" aria-label="Plano de voo">
      <div className="plan-row">
        <input
          type="text"
          aria-label="Nome do plano"
          placeholder="Nome do plano, ex.: mapeamento norte"
          maxLength={120}
          value={planName}
          onChange={(e) => {
            setPlanName(e.target.value);
          }}
        />
        <button
          type="button"
          className="primary"
          disabled={busy || !canSave || (!dirty && planId !== null)}
          onClick={() => void savePlan()}
        >
          Salvar
        </button>
      </div>

      <div className="plan-row">
        <select
          aria-label="Abrir plano salvo"
          value={planId ?? ""}
          onChange={(e) => {
            if (e.target.value && confirmDiscard()) openPlan(e.target.value);
          }}
        >
          <option value="">
            {plans.length ? `Planos salvos (${plans.length.toString()})` : "Nenhum plano salvo"}
          </option>
          {plans.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} · {STATUS_LABEL[p.status]}
            </option>
          ))}
        </select>
      </div>

      <div className="plan-row">
        <button
          type="button"
          className="secondary"
          onClick={() => {
            if (confirmDiscard()) newPlan();
          }}
        >
          Novo
        </button>
        <button
          type="button"
          className="secondary"
          disabled={busy || !planId || !canSave}
          onClick={() => void savePlan({ asCopy: true })}
        >
          Duplicar
        </button>
        <button
          type="button"
          className="secondary danger"
          disabled={busy || !planId}
          onClick={() => {
            const plan = plans.find((p) => p.id === planId);
            if (plan && window.confirm(`Apagar o plano “${plan.name}”?`)) void removePlan(plan.id);
          }}
        >
          Apagar
        </button>
        <span className={`plan-state${dirty ? " plan-state-dirty" : ""}`} role="status">
          {busy ? "Salvando…" : dirty ? "● alterações não salvas" : planId ? "✓ salvo" : ""}
        </span>
      </div>

      {error && (
        <p role="alert" className="error-text">
          {error}
        </p>
      )}
    </section>
  );
}
