import { useEffect, useState } from "react";

import { fetchProjects, fetchProjectTasks } from "../api/client";
import type { WebodmProject, WebodmTask } from "../api/types";
import { useStore } from "../store";
import { writeAddress } from "./address";

const COMPLETED = 40;
const MAP_ASSETS = ["orthophoto.tif", "dsm.tif", "dtm.tif"];

/** The box that holds every task's extent, as [[south, west], [north, east]]; null if none has one. */
export function unionBounds(
  tasks: readonly WebodmTask[],
): [[number, number], [number, number]] | null {
  const extents = tasks.flatMap((t) => (t.extent ? [t.extent] : []));
  if (extents.length === 0) return null;
  return [
    [Math.min(...extents.map((e) => e[1])), Math.min(...extents.map((e) => e[0]))],
    [Math.max(...extents.map((e) => e[3])), Math.max(...extents.map((e) => e[2]))],
  ];
}

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
  const projectId = useStore((s) => s.projectId);
  const setProject = useStore((s) => s.setProject);
  const showBounds = useStore((s) => s.showBounds);

  const projects: WebodmProject[] | null = useAsync(() => fetchProjects(), "projects");
  const tasks: WebodmTask[] | null = useAsync(
    () => (projectId === null ? Promise.resolve([]) : fetchProjectTasks(projectId)),
    projectId,
  );

  // A project the user has not drawn on yet: land on the ground its earlier flights covered
  useEffect(() => {
    const bounds = tasks && !task ? unionBounds(tasks) : null;
    if (bounds && useStore.getState().points.length === 0) showBounds(bounds);
  }, [tasks, task, showBounds]);

  const pick = (id: string) => {
    writeAddress(projectId, id);
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
            void setProject(id);
            if (task && Number(task.project) !== id) clearTask(); // that task is of another project
            writeAddress(id, task && Number(task.project) === id ? task.id : "");
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
