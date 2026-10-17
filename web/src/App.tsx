import { useEffect } from "react";

import { MapView } from "./map/MapView";
import { Panel } from "./panel/Panel";
import { useStore } from "./store";

export function App() {
  const loadDrones = useStore((s) => s.loadDrones);
  const loadTask = useStore((s) => s.loadTask);
  const task = useStore((s) => s.task);
  useEffect(() => {
    void loadDrones();
    const taskId = new URLSearchParams(window.location.search).get("task");
    if (taskId) void loadTask(taskId);
  }, [loadDrones, loadTask]);

  return (
    <div className="app">
      <header className="app-header">
        <span className="logo">maps4drone</span>
        <span className="tagline">Planejador de missões de drone</span>
        {task && <span className="task-chip">Projeto: {task.name}</span>}
      </header>
      <main className="app-main">
        <MapView />
        <Panel />
      </main>
    </div>
  );
}
