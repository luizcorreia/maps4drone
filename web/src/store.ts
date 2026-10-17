import { create } from "zustand";

import {
  deletePlan,
  exportMission,
  fetchDrones,
  fetchPlans,
  fetchTask,
  planMission,
  savePlan,
} from "./api/client";
import { modeInfo, pointsFromGeometry, toGeometry } from "./api/geometry";
import type {
  Camera,
  DemSource,
  Drone,
  LngLat,
  MissionFile,
  Mode,
  Params,
  PlanRequest,
  PlanResult,
  SavedPlan,
  TaskContext,
} from "./api/types";

export type Status = "idle" | "planning" | "ready" | "error";

const PLAN_DELAY_MS = 300;
/** Terrain following calls an online elevation service, so wait for the edits to settle. */
const TERRAIN_PLAN_DELAY_MS = 1000;
const PREFERRED_INTERVAL_S = 2;

export const DEFAULT_PARAMS: Params = {
  drone: "atom2",
  camera: null,
  altitude: 80,
  front: 80,
  side: 70,
  angle: null,
  interval: PREFERRED_INTERVAL_S,
  pitch: -90,
  margin: 0,
  speed: 5,
  terrain: false,
  takeoff: null,
  terrain_step: 30,
  lines: 3,
  radius: 40,
  points: 12,
  target_height: 0,
  photo_each: false,
  wall_height: 20,
  standoff: 15,
  wall_side: "left",
};

interface State {
  drones: Drone[];
  mode: Mode;
  points: LngLat[];
  params: Params;
  plan: PlanResult | null;
  status: Status;
  error: string | null;
  /** The next map click sets the takeoff point instead of drawing. */
  pickingTakeoff: boolean;
  /** Bumped when points arrive from outside the map, so the map re-frames them. */
  fitSignal: number;
  /** Where the map should go next ([[south, west], [north, east]]); `seq` makes a repeat count. */
  viewTarget: { bounds: [[number, number], [number, number]]; seq: number } | null;
  /** The WebODM task the page was opened for, if any. */
  task: TaskContext | null;
  demSource: DemSource;
  /** The WebODM project the plans are kept under; null for the public, unsaved mode. */
  projectId: number | null;
  plans: SavedPlan[];
  /** The saved plan on the screen, or null for a drawing that was never saved. */
  planId: string | null;
  planName: string;
  /** The name and request as last saved or opened, to tell whether anything changed since. */
  savedSnapshot: string | null;
  plansError: string | null;
  plansBusy: boolean;

  loadDrones: () => Promise<void>;
  loadTask: (id: string) => Promise<void>;
  clearTask: () => void;
  setProject: (id: number | null) => Promise<void>;
  showBounds: (bounds: [[number, number], [number, number]]) => void;
  setPlanName: (name: string) => void;
  savePlan: (options?: { asCopy?: boolean }) => Promise<void>;
  openPlan: (id: string) => void;
  newPlan: () => void;
  removePlan: (id: string) => Promise<void>;
  setDemSource: (source: DemSource) => void;
  setMode: (mode: Mode) => void;
  setDrone: (id: string) => void;
  setParam: <K extends keyof Params>(key: K, value: Params[K]) => void;
  applyPreset: (mode: Mode, params: Partial<Params>) => void;
  importPoints: (points: LngLat[]) => void;
  undoPoint: () => void;
  setPickingTakeoff: (picking: boolean) => void;
  setPoints: (points: LngLat[]) => void;
  addPoint: (point: LngLat) => void;
  movePoint: (index: number, point: LngLat) => void;
  removePoint: (index: number) => void;
  clearPoints: () => void;
  exportMission: () => Promise<MissionFile>;
}

export const selectDrone = (s: Pick<State, "drones" | "params">): Drone | undefined =>
  s.drones.find((d) => d.id === s.params.drone);

export const selectCamera = (s: Pick<State, "drones" | "params">): Camera | undefined => {
  const drone = selectDrone(s);
  return drone?.cameras[s.params.camera ?? drone.default_camera];
};

/** The request for what is on the map, or null while the plan cannot be computed yet. */
export function selectRequest(
  s: Pick<State, "mode" | "points" | "params"> & Partial<Pick<State, "task" | "demSource">>,
): PlanRequest | null {
  const geometry = toGeometry(s.mode, s.points);
  if (!geometry) return null;
  if (s.params.terrain && !s.params.takeoff) return null;
  const request: PlanRequest = { mode: s.mode, geometry, params: s.params };
  if (s.task && s.params.terrain && s.demSource && s.demSource !== "online") {
    request.dem = { layer: s.demSource };
  }
  return request;
}

const snapshotOf = (name: string, request: PlanRequest | null): string | null =>
  request ? JSON.stringify({ name: name.trim(), request }) : null;

/** True when the drawing or its name differ from what was last saved (or was never saved). */
export function selectDirty(
  s: Pick<
    State,
    "mode" | "points" | "params" | "task" | "demSource" | "planName" | "savedSnapshot"
  >,
): boolean {
  return snapshotOf(s.planName, selectRequest(s)) !== s.savedSnapshot;
}

const messageOf = (err: unknown): string => (err instanceof Error ? err.message : String(err));

/** The project's own model if it has one: it is sharper than the online one and has no quota. */
function defaultDemSource(task: TaskContext): DemSource {
  if (task.assets.dsm) return "dsm";
  return task.assets.dtm ? "dtm" : "online";
}

/** Drone-dependent params that stay valid after a drone switch. */
function paramsForDrone(params: Params, drone: Drone): Params {
  const interval = drone.shoot_intervals_s.includes(params.interval)
    ? params.interval
    : drone.shoot_intervals_s.includes(PREFERRED_INTERVAL_S)
      ? PREFERRED_INTERVAL_S
      : (drone.shoot_intervals_s[0] ?? params.interval);
  return {
    ...params,
    drone: drone.id,
    camera: null,
    interval,
    altitude: Math.min(params.altitude, drone.max_height_m),
  };
}

let timer: ReturnType<typeof setTimeout> | undefined;
let inflight: AbortController | undefined;

export const useStore = create<State>()((set, get) => {
  /** Debounced: runs 300 ms after the last change, dropping any request still in flight. */
  function replan(): void {
    clearTimeout(timer);
    inflight?.abort();
    const request = selectRequest(get());
    if (!request) {
      set({ plan: null, status: "idle", error: null });
      return;
    }
    set({ status: "planning" });
    timer = setTimeout(
      () => {
        const controller = new AbortController();
        inflight = controller;
        planMission(request, { taskId: get().task?.id, signal: controller.signal }).then(
          (plan) => {
            if (controller.signal.aborted) return;
            set({ plan, status: "ready", error: null });
          },
          (err: unknown) => {
            if (controller.signal.aborted) return;
            set({
              plan: null,
              status: "error",
              error: err instanceof Error ? err.message : String(err),
            });
          },
        );
      },
      request.params.terrain ? TERRAIN_PLAN_DELAY_MS : PLAN_DELAY_MS,
    );
  }

  const edit = (patch: Partial<Pick<State, "points" | "params" | "mode">>) => {
    set(patch);
    replan();
  };

  return {
    drones: [],
    mode: "grid",
    points: [],
    params: DEFAULT_PARAMS,
    plan: null,
    status: "idle",
    error: null,
    pickingTakeoff: false,
    fitSignal: 0,
    viewTarget: null,
    task: null,
    demSource: "online",
    projectId: null,
    plans: [],
    planId: null,
    planName: "",
    savedSnapshot: null,
    plansError: null,
    plansBusy: false,

    loadDrones: async () => {
      let drones: Drone[];
      try {
        drones = await fetchDrones();
      } catch (err) {
        set({ status: "error", error: err instanceof Error ? err.message : String(err) });
        return;
      }
      const current = drones.find((d) => d.id === get().params.drone) ?? drones[0];
      set({ drones });
      if (current) edit({ params: paramsForDrone(get().params, current) });
    },

    loadTask: async (id) => {
      try {
        const task = await fetchTask(id);
        set({ task, demSource: defaultDemSource(task) });
        if (get().projectId !== Number(task.project)) await get().setProject(Number(task.project));
        replan();
      } catch (err) {
        set({ status: "error", error: err instanceof Error ? err.message : String(err) });
      }
    },

    setProject: async (id) => {
      set({ projectId: id, plans: [], planId: null, savedSnapshot: null, plansError: null });
      if (id === null) return;
      try {
        const plans = await fetchPlans(id);
        if (get().projectId === id) set({ plans });
      } catch (err) {
        if (get().projectId === id) set({ plansError: messageOf(err) });
      }
    },

    showBounds: (bounds) => {
      set({ viewTarget: { bounds, seq: (get().viewTarget?.seq ?? 0) + 1 } });
    },

    setPlanName: (planName) => {
      set({ planName });
    },

    savePlan: async ({ asCopy = false } = {}) => {
      const { projectId, planId, planName } = get();
      const request = selectRequest(get());
      if (projectId === null) return;
      const name = asCopy ? `${planName.trim()} (cópia)` : planName.trim();
      if (!name) {
        set({ plansError: "Dê um nome ao plano." });
        return;
      }
      if (!request) {
        set({ plansError: "Desenhe a área e confira os ajustes antes de salvar." });
        return;
      }
      set({ plansBusy: true, plansError: null });
      try {
        const saved = await savePlan(projectId, {
          ...(planId && !asCopy ? { id: planId } : {}),
          name,
          request,
        });
        if (get().projectId !== projectId) return;
        set({
          plans: [saved, ...get().plans.filter((p) => p.id !== saved.id)],
          planId: saved.id,
          planName: saved.name,
          savedSnapshot: snapshotOf(saved.name, request),
        });
      } catch (err) {
        set({ plansError: messageOf(err) });
      } finally {
        set({ plansBusy: false });
      }
    },

    openPlan: (id) => {
      const plan = get().plans.find((p) => p.id === id);
      if (!plan) return;
      const { mode, geometry, params, dem } = plan.request;
      const drone = get().drones.find((d) => d.id === params.drone);
      set({
        mode,
        points: geometry ? pointsFromGeometry(geometry) : [],
        params: { ...(drone ? paramsForDrone(DEFAULT_PARAMS, drone) : DEFAULT_PARAMS), ...params },
        demSource:
          dem?.layer ?? (get().task ? defaultDemSource(get().task as TaskContext) : "online"),
        planId: plan.id,
        planName: plan.name,
        plansError: null,
        fitSignal: get().fitSignal + 1,
      });
      set({ savedSnapshot: snapshotOf(plan.name, selectRequest(get())) });
      replan();
    },

    newPlan: () => {
      set({
        points: [],
        planId: null,
        planName: "",
        savedSnapshot: null,
        plansError: null,
        plan: null,
        status: "idle",
        error: null,
      });
      replan();
    },

    removePlan: async (id) => {
      const { projectId } = get();
      if (projectId === null) return;
      set({ plansBusy: true, plansError: null });
      try {
        await deletePlan(projectId, id);
        const forgotten = get().planId === id;
        set({
          plans: get().plans.filter((p) => p.id !== id),
          ...(forgotten ? { planId: null, savedSnapshot: null } : {}),
        });
      } catch (err) {
        set({ plansError: messageOf(err) });
      } finally {
        set({ plansBusy: false });
      }
    },

    clearTask: () => {
      set({ task: null, demSource: "online" });
      replan();
    },

    setDemSource: (demSource) => {
      set({ demSource });
      replan();
    },

    setMode: (mode) => {
      const { points, mode: previous } = get();
      const next = modeInfo(mode);
      const kept = next.shape === modeInfo(previous).shape ? points.slice(0, next.max) : [];
      edit({ mode, points: kept });
    },

    setDrone: (id) => {
      const drone = get().drones.find((d) => d.id === id);
      if (drone) edit({ params: paramsForDrone(get().params, drone) });
    },

    setParam: (key, value) => {
      edit({ params: { ...get().params, [key]: value } });
    },

    applyPreset: (mode, patch) => {
      const { points, mode: previous, params } = get();
      const next = modeInfo(mode);
      const kept = next.shape === modeInfo(previous).shape ? points.slice(0, next.max) : [];
      const drone = selectDrone(get());
      const merged = { ...params, ...patch };
      if (drone) merged.altitude = Math.min(merged.altitude, drone.max_height_m);
      edit({ mode, points: kept, params: merged });
    },

    importPoints: (points) => {
      edit({ points: points.slice(0, modeInfo(get().mode).max) });
      set({ fitSignal: get().fitSignal + 1 });
    },

    undoPoint: () => {
      edit({ points: get().points.slice(0, -1) });
    },

    setPickingTakeoff: (pickingTakeoff) => {
      set({ pickingTakeoff });
    },

    setPoints: (points) => {
      edit({ points: points.slice(0, modeInfo(get().mode).max) });
    },

    addPoint: (point) => {
      const { points, mode } = get();
      if (points.length < modeInfo(mode).max) edit({ points: [...points, point] });
    },

    movePoint: (index, point) => {
      edit({ points: get().points.map((p, i) => (i === index ? point : p)) });
    },

    removePoint: (index) => {
      edit({ points: get().points.filter((_, i) => i !== index) });
    },

    clearPoints: () => {
      edit({ points: [] });
    },

    exportMission: async () => {
      const request = selectRequest(get());
      if (!request) throw new Error("Nada para exportar: desenhe a área e confira os ajustes.");
      return exportMission(request, { taskId: get().task?.id });
    },
  };
});
