import { useEffect } from "react";

import { insideWebodm } from "./api/client";
import { MapView } from "./map/MapView";
import { Panel } from "./panel/Panel";
import { useStore } from "./store";
import { TaskPicker } from "./ui/TaskPicker";

export function App() {
  const loadDrones = useStore((s) => s.loadDrones);
  const loadTask = useStore((s) => s.loadTask);
  const task = useStore((s) => s.task);
  const webodm = insideWebodm();
  useEffect(() => {
    void loadDrones();
    const taskId = new URLSearchParams(window.location.search).get("task");
    if (taskId) void loadTask(taskId);
  }, [loadDrones, loadTask]);

  return (
    <div className="app">
      <header className="app-header">
        {webodm && (
          <a
            className="back-link"
            href={task ? `/dashboard/?project_id=${String(task.project)}` : "/dashboard/"}
            title="Voltar ao WebODM"
          >
            ← WebODM
          </a>
        )}
        <span className="logo">maps4drone</span>
        <span className="tagline">Planejador de missões de drone</span>
        {webodm && <TaskPicker />}
      </header>
      <main className="app-main">
        <MapView />
        <Panel />
      </main>
    </div>
  );
}
