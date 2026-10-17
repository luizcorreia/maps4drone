import { useEffect, useState } from "react";

import { fetchProjects, fetchProjectTasks } from "../api/client";
import type { WebodmProject, WebodmTask } from "../api/types";
import { useStore } from "../store";

const COMPLETED = 40;
const MAP_ASSETS = ["orthophoto.tif", "dsm.tif", "dtm.tif"];

/** Only completed tasks with a map are worth planning over. */
export const hasMap = (task: WebodmTask): boolean =>
  task.status === COMPLETED && MAP_ASSETS.some((a) => task.available_assets?.includes(a));

function useAsync<T>(load: () => Promise<T>, key: unknown): T | null {
  const [value, setValue] = useState<{ key: unknown; data: T } | null>(null);
  useEffect(() => {
    let live = true;
    load().then(
      (data) => {
        if (live) setValue({ key, data });
      },
      () => undefined,
    );
    return () => {
      live = false;
    };
    // `load` is rebuilt on every render; the key says when the data is really wanted again
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return value !== null && value.key === key ? value.data : null;
}

/** Chooses the WebODM project and task to plan over, from the user's own projects. */
export function TaskPicker() {
  const task = useStore((s) => s.task);
  const loadTask = useStore((s) => s.loadTask);
  const clearTask = useStore((s) => s.clearTask);
  const [chosen, setChosen] = useState<number | null>(null);
  const projectId = chosen ?? (task ? Number(task.project) : null);

  const projects: WebodmProject[] | null = useAsync(() => fetchProjects(), "projects");
  const tasks: WebodmTask[] | null = useAsync(
    () => (projectId === null ? Promise.resolve([]) : fetchProjectTasks(projectId)),
    projectId,
  );

  const pick = (id: string) => {
    const url = new URL(window.location.href);
    if (id) url.searchParams.set("task", id);
    else url.searchParams.delete("task");
    window.history.replaceState(null, "", url);
    if (id) void loadTask(id);
    else clearTask();
  };
  const mapTasks = (tasks ?? []).filter(hasMap);

  return (
    <div className="task-picker">
      <label>
        <span className="sr-only">Projeto</span>
        <select
          aria-label="Projeto do WebODM"
          value={projectId ?? ""}
          onChange={(e) => {
            const id = e.target.value ? Number(e.target.value) : null;
            setChosen(id);
            if (id === null) pick("");
          }}
        >
          <option value="">Sem projeto (mapas públicos)</option>
          {projects?.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </label>
      {projectId !== null && (
        <label>
          <span className="sr-only">Tarefa</span>
          <select
            aria-label="Tarefa do projeto"
            value={task?.id ?? ""}
            onChange={(e) => {
              pick(e.target.value);
            }}
          >
            <option value="">
              {tasks === null
                ? "Carregando…"
                : mapTasks.length
                  ? "Escolha uma tarefa"
                  : "Nenhuma tarefa com mapa"}
            </option>
            {mapTasks.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name ?? t.id}
              </option>
            ))}
          </select>
        </label>
      )}
    </div>
  );
}
