import { useStore } from "../store";
import { writeAddress } from "../ui/address";

/**
 * What to do once the photos are processed: tie the plan to that task (making it "realizado"),
 * and see where the aircraft really took its pictures against what was planned.
 */
export function AfterFlight() {
  const projectId = useStore((s) => s.projectId);
  const task = useStore((s) => s.task);
  const plan = useStore((s) => s.plans.find((p) => p.id === s.planId));
  const busy = useStore((s) => s.plansBusy);
  const showShots = useStore((s) => s.showShots);
  const shots = useStore((s) => s.shots);
  const shotsError = useStore((s) => s.shotsError);
  const planned = useStore((s) =>
    s.plan?.interval == null ? undefined : s.plan.stats.images[String(s.plan.interval)],
  );
  const { linkPlanToTask, setShowShots, loadTask } = useStore.getState();

  const taskInProject = task !== null && Number(task.project) === projectId;
  if (!plan && !taskInProject) return null;

  const linkedHere = plan?.task_id != null && plan.task_id === task?.id;

  return (
    <section className="after-flight" aria-label="Depois do voo">
      {plan && (
        <div className="after-row">
          {linkedHere ? (
            <>
              <span className="after-state">✓ Realizado nesta tarefa</span>
              <button
                type="button"
                className="secondary"
                disabled={busy}
                onClick={() => void linkPlanToTask(null)}
              >
                Desvincular
              </button>
            </>
          ) : plan.task_id ? (
            <>
              <span className="after-state">Realizado em outra tarefa</span>
              <button
                type="button"
                className="secondary"
                onClick={() => {
                  if (plan.task_id) {
                    writeAddress(projectId, plan.task_id);
                    void loadTask(plan.task_id);
                  }
                }}
              >
                Abrir a tarefa
              </button>
            </>
          ) : taskInProject ? (
            <button
              type="button"
              className="secondary"
              disabled={busy}
              title="Marca o plano como realizado, com as fotos desta tarefa"
              onClick={() => void linkPlanToTask(task.id)}
            >
              Vincular à tarefa «{task.name}»
            </button>
          ) : (
            <span className="muted">Abra a tarefa processada para vincular este plano.</span>
          )}
        </div>
      )}

      {task?.assets.shots && taskInProject && (
        <label className="after-shots">
          <input
            type="checkbox"
            checked={showShots}
            onChange={(e) => void setShowShots(e.target.checked)}
          />
          <span>
            Mostrar onde as fotos foram tiradas
            {shots && (
              <>
                {" "}
                <strong>
                  ({shots.length.toString()} tiradas
                  {planned === undefined ? "" : ` · ${planned.toString()} planejadas`})
                </strong>
              </>
            )}
          </span>
        </label>
      )}
      {shotsError && (
        <p role="alert" className="error-text">
          {shotsError}
        </p>
      )}
    </section>
  );
}
