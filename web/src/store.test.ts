import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "./api/client";
import type { Drone, PlanResult } from "./api/types";
import { DEFAULT_PARAMS, selectRequest, useStore } from "./store";

vi.mock("./api/client");

const camera = {
  name: "c",
  sensor_w_mm: 6.4,
  sensor_h_mm: 4.8,
  focal_mm: 4.5,
  image_w: 4000,
  image_h: 3000,
  rolling_shutter_ms: 0,
};

const drone = (id: string, intervals: number[], maxHeight = 120): Drone => ({
  id,
  name: id,
  cameras: { c: camera },
  default_camera: "c",
  flight_minutes: 30,
  max_speed_ms: 15,
  max_height_m: maxHeight,
  shoot_intervals_s: intervals,
  export_format: "atom2",
  dji_enums: null,
});

const PLAN = { stats: { waypoints: 4 } } as PlanResult;
const SQUARE: [number, number][] = [
  [-51.9, -23.15],
  [-51.89, -23.15],
  [-51.89, -23.14],
];

beforeEach(() => {
  vi.useFakeTimers();
  vi.mocked(client.planMission).mockResolvedValue(PLAN);
  useStore.setState({
    drones: [drone("atom2", [2, 3, 5]), drone("other", [3, 5], 60)],
    mode: "grid",
    points: [],
    params: DEFAULT_PARAMS,
    plan: null,
    status: "idle",
    error: null,
    task: null,
    demSource: "online",
  });
});

afterEach(() => {
  vi.useRealTimers();
  vi.resetAllMocks();
});

describe("planning", () => {
  it("waits for enough points before asking the server", async () => {
    useStore.getState().setPoints(SQUARE.slice(0, 2));
    await vi.advanceTimersByTimeAsync(500);
    expect(client.planMission).not.toHaveBeenCalled();
    expect(useStore.getState().status).toBe("idle");
  });

  it("debounces a burst of edits into one request", async () => {
    const { setPoints, setParam } = useStore.getState();
    setPoints(SQUARE);
    setParam("altitude", 90);
    setParam("altitude", 95);
    expect(useStore.getState().status).toBe("planning");
    await vi.advanceTimersByTimeAsync(300);
    expect(client.planMission).toHaveBeenCalledTimes(1);
    expect(vi.mocked(client.planMission).mock.calls[0]?.[0].params.altitude).toBe(95);
    expect(useStore.getState()).toMatchObject({ status: "ready", plan: PLAN });
  });

  it("surfaces the server's message and clears the stale plan", async () => {
    vi.mocked(client.planMission).mockRejectedValue(new Error("poligono invalido"));
    useStore.getState().setPoints(SQUARE);
    await vi.advanceTimersByTimeAsync(300);
    expect(useStore.getState()).toMatchObject({
      status: "error",
      error: "poligono invalido",
      plan: null,
    });
  });

  it("does not plan terrain following without a takeoff point", () => {
    useStore.setState({ points: SQUARE });
    useStore.getState().setParam("terrain", true);
    expect(useStore.getState().status).toBe("idle");
    useStore.getState().setParam("takeoff", [-51.9, -23.15]);
    expect(useStore.getState().status).toBe("planning");
  });

  it("waits longer before asking for terrain, which hits an online service", async () => {
    useStore.setState({ points: SQUARE });
    useStore.getState().setParam("takeoff", [-51.9, -23.15]);
    useStore.getState().setParam("terrain", true);
    await vi.advanceTimersByTimeAsync(500);
    expect(client.planMission).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(600);
    expect(client.planMission).toHaveBeenCalledTimes(1);
  });

  it("ignores the result of a request that was superseded", async () => {
    let resolveFirst: (p: PlanResult) => void = () => undefined;
    vi.mocked(client.planMission).mockImplementationOnce(
      () =>
        new Promise<PlanResult>((resolve) => {
          resolveFirst = resolve;
        }),
    );
    useStore.getState().setPoints(SQUARE);
    await vi.advanceTimersByTimeAsync(300);
    useStore.getState().clearPoints();
    resolveFirst(PLAN);
    await vi.advanceTimersByTimeAsync(0);
    expect(useStore.getState()).toMatchObject({ status: "idle" });
  });
});

describe("loadDrones", () => {
  it("loads the catalog and adopts the first drone's limits", async () => {
    vi.mocked(client.fetchDrones).mockResolvedValue([drone("atom2", [3, 5], 60)]);
    useStore.setState({ drones: [] });
    await useStore.getState().loadDrones();
    expect(useStore.getState().drones).toHaveLength(1);
    expect(useStore.getState().params).toMatchObject({ interval: 3, altitude: 60 });
  });

  it("reports an unreachable server instead of throwing", async () => {
    vi.mocked(client.fetchDrones).mockRejectedValue(new Error("sem servidor"));
    await useStore.getState().loadDrones();
    expect(useStore.getState()).toMatchObject({ status: "error", error: "sem servidor" });
  });
});

describe("modes and points", () => {
  it("keeps the points between modes that draw the same shape", () => {
    const { setPoints, setMode } = useStore.getState();
    setPoints(SQUARE);
    setMode("double_grid");
    expect(useStore.getState().points).toEqual(SQUARE);
    setMode("orbit");
    expect(useStore.getState().points).toEqual([]);
  });

  it("truncates to the mode's maximum", () => {
    const { setPoints, setMode } = useStore.getState();
    setMode("corridor");
    setPoints(SQUARE);
    setMode("facade");
    expect(useStore.getState().points).toEqual(SQUARE.slice(0, 2));
    useStore.getState().addPoint([0, 0]);
    expect(useStore.getState().points).toHaveLength(2);
  });

  it("moves and removes points by index", () => {
    const { setPoints, movePoint, removePoint } = useStore.getState();
    setPoints(SQUARE);
    movePoint(1, [1, 1]);
    expect(useStore.getState().points[1]).toEqual([1, 1]);
    removePoint(0);
    expect(useStore.getState().points).toHaveLength(2);
  });
});

describe("drone switch", () => {
  it("falls back to a valid interval and clamps the altitude", () => {
    useStore.getState().setParam("altitude", 100);
    useStore.getState().setDrone("other");
    expect(useStore.getState().params).toMatchObject({
      drone: "other",
      interval: 3,
      altitude: 60,
      camera: null,
    });
  });

  it("keeps an interval the new drone also supports", () => {
    useStore.getState().setDrone("other");
    useStore.getState().setDrone("atom2");
    expect(useStore.getState().params.interval).toBe(3);
  });
});

const TASK = {
  id: "t1",
  project: 3,
  name: "Fazenda",
  extent: [-51.9, -23.1, -51.8, -23.0] as [number, number, number, number],
  assets: { orthophoto: true, dsm: true, dtm: false },
  tiles: "/api/projects/3/tasks/t1/orthophoto/tiles/{z}/{x}/{y}.png",
};

describe("WebODM task", () => {
  it("loads the task and prefers its DSM, then its DTM, then the online model", async () => {
    vi.mocked(client.fetchTask).mockResolvedValue(TASK);
    await useStore.getState().loadTask("t1");
    expect(useStore.getState()).toMatchObject({ task: TASK, demSource: "dsm" });
    vi.mocked(client.fetchTask).mockResolvedValue({
      ...TASK,
      assets: { ...TASK.assets, dsm: false, dtm: true },
    });
    await useStore.getState().loadTask("t1");
    expect(useStore.getState().demSource).toBe("dtm");
    vi.mocked(client.fetchTask).mockResolvedValue({
      ...TASK,
      assets: { ...TASK.assets, dsm: false },
    });
    await useStore.getState().loadTask("t1");
    expect(useStore.getState().demSource).toBe("online");
  });

  it("reports a task that cannot be opened", async () => {
    vi.mocked(client.fetchTask).mockRejectedValue(new Error("Sem permissão"));
    await useStore.getState().loadTask("nope");
    expect(useStore.getState()).toMatchObject({
      status: "error",
      error: "Sem permissão",
      task: null,
    });
  });

  it("asks for the model only when following terrain inside a task", () => {
    const base = { mode: "grid" as const, points: SQUARE, task: TASK, demSource: "dsm" as const };
    const flat = selectRequest({ ...base, params: DEFAULT_PARAMS });
    expect(flat?.dem).toBeUndefined();
    const params = {
      ...DEFAULT_PARAMS,
      terrain: true,
      takeoff: [-51.9, -23.15] as [number, number],
    };
    expect(selectRequest({ ...base, params })?.dem).toEqual({ layer: "dsm" });
    expect(selectRequest({ ...base, params, demSource: "online" })?.dem).toBeUndefined();
    expect(selectRequest({ ...base, params, task: null })?.dem).toBeUndefined();
  });

  it("plans against the task and replans when the model changes", async () => {
    vi.mocked(client.fetchTask).mockResolvedValue(TASK);
    await useStore.getState().loadTask("t1");
    useStore.setState({ points: SQUARE });
    useStore.getState().setParam("takeoff", [-51.9, -23.15]);
    useStore.getState().setParam("terrain", true);
    await vi.advanceTimersByTimeAsync(1100);
    expect(client.planMission).toHaveBeenCalledTimes(1);
    const [request, options] = vi.mocked(client.planMission).mock.calls[0] ?? [];
    expect(request?.dem).toEqual({ layer: "dsm" });
    expect(options?.taskId).toBe("t1");
    useStore.getState().setDemSource("online");
    await vi.advanceTimersByTimeAsync(1100);
    expect(client.planMission).toHaveBeenCalledTimes(2);
    expect(vi.mocked(client.planMission).mock.calls[1]?.[0].dem).toBeUndefined();
  });
});

describe("selectRequest", () => {
  it("builds the GeoJSON for the current mode", () => {
    const req = selectRequest({
      mode: "grid",
      points: SQUARE,
      params: DEFAULT_PARAMS,
    });
    expect(req?.geometry).toEqual({
      type: "Polygon",
      coordinates: [[...SQUARE, SQUARE[0]]],
    });
  });
});

describe("export", () => {
  it("refuses when there is nothing to export", async () => {
    await expect(useStore.getState().exportMission()).rejects.toThrow("Nada para exportar");
  });
});
