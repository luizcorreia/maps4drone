import { useEffect } from "react";

import { MapView } from "./map/MapView";
import { Panel } from "./panel/Panel";
import { useStore } from "./store";

export function App() {
  const loadDrones = useStore((s) => s.loadDrones);
  useEffect(() => {
    void loadDrones();
  }, [loadDrones]);

  return (
    <div className="app">
      <header className="app-header">
        <span className="logo">maps4drone</span>
        <span className="tagline">Planejador de missões de drone</span>
      </header>
      <main className="app-main">
        <MapView />
        <Panel />
      </main>
    </div>
  );
}
