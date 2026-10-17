import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import type { Drone, LngLat, PlanResult } from "../api/types";
import { DEFAULT_PARAMS, useStore } from "../store";
import { Panel } from "./Panel";

vi.mock("../api/client");

const camera = {
  name: "c",
  sensor_w_mm: 6.4,
  sensor_h_mm: 4.8,
  focal_mm: 4.5,
  image_w: 4000,
  image_h: 3000,
  rolling_shutter_ms: 0,
};

const drone = (id: string, format: "atom2" | "dji"): Drone => ({
  id,
  name: id === "atom2" ? "Potensic Atom 2" : "DJI Mini 4 Pro",
  cameras: { c: camera },
  default_camera: "c",
  flight_minutes: 30,
  max_speed_ms: 15,
  max_height_m: 120,
  shoot_intervals_s: [2, 3, 5],
  export_format: format,
  dji_enums: null,
});

const SQUARE: LngLat[] = [
  [-51.9, -23.15],
  [-51.89, -23.15],
  [-51.89, -23.14],
];

const PLAN = {
  geojson: { type: "FeatureCollection", features: [] },
  stats: {
    waypoints: 12,
    distance_m: 1500,
    duration_s: 185,
    batteries: 1,
    images: { "2": 40 },
    area_ha: 3.2,
  },
  warnings: ["altura acima do limite"],
  speed: 6.5,
  interval: 2,
} as unknown as PlanResult;

beforeEach(() => {
  vi.mocked(client.planMission).mockResolvedValue(PLAN);
  useStore.setState({
    drones: [drone("atom2", "atom2"), drone("mini4pro", "dji")],
    mode: "grid",
    points: [],
    params: DEFAULT_PARAMS,
    plan: null,
    status: "idle",
    error: null,
    pickingTakeoff: false,
    task: null,
    demSource: "online",
  });
});

afterEach(() => {
  vi.resetAllMocks();
});

const step = (name: string) => screen.getByRole("button", { name: new RegExp(name) });

describe("Panel", () => {
  it("starts on the mission step and applies a preset", async () => {
    render(<Panel />);
    await userEvent.click(screen.getByRole("radio", { name: /Modelo 3D/ }));
    expect(useStore.getState().mode).toBe("double_grid");
    expect(screen.getByRole("radio", { name: /Modelo 3D/ })).toHaveAttribute(
      "aria-checked",
      "true",
    );
  });

  it("blocks the next steps until the area is drawn", async () => {
    render(<Panel />);
    await userEvent.click(screen.getByRole("button", { name: "Próximo" }));
    expect(screen.getByRole("heading", { name: /Marque a área/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Próximo" })).toBeDisabled();
    expect(step("Ajustes")).toBeDisabled();
    expect(step("Revisar")).toBeDisabled();
    act(() => {
      useStore.setState({ points: SQUARE });
    });
    expect(screen.getByRole("button", { name: "Próximo" })).toBeEnabled();
    expect(step("Ajustes")).toBeEnabled();
  });

  it("counts points and undoes the last one", async () => {
    useStore.setState({ points: SQUARE.slice(0, 2) });
    render(<Panel />);
    await userEvent.click(step("Área"));
    expect(screen.getByText(/2 pontos · faltam 1/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Desfazer último" }));
    expect(useStore.getState().points).toHaveLength(1);
  });

  it("imports a polygon from a file and reports an unusable one", async () => {
    vi.mocked(client.importFile).mockResolvedValueOnce({
      polygon: { type: "Polygon", coordinates: [[...SQUARE, SQUARE[0] as LngLat]] },
      line: null,
    });
    const { container } = render(<Panel />);
    await userEvent.click(step("Área"));
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    await userEvent.upload(input as HTMLInputElement, new File(["x"], "area.kml"));
    await waitFor(() => {
      expect(useStore.getState().points).toEqual(SQUARE);
    });

    vi.mocked(client.importFile).mockResolvedValueOnce({ polygon: null, line: null });
    await userEvent.upload(input as HTMLInputElement, new File(["x"], "vazio.kml"));
    expect(await screen.findByRole("alert")).toHaveTextContent("não tem a área");
  });

  it("shows the settings of the current mode only", async () => {
    useStore.setState({ points: SQUARE });
    render(<Panel />);
    await userEvent.click(step("Ajustes"));
    expect(screen.getByLabelText("Sobreposição frontal")).toBeInTheDocument();
    expect(screen.queryByLabelText("Raio")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Ângulo automático")).toBeChecked();
    await userEvent.click(screen.getByLabelText("Ângulo automático"));
    expect(useStore.getState().params.angle).toBe(0);
    expect(screen.getByLabelText("Ângulo das faixas")).toBeInTheDocument();
  });

  it("only accepts an odd number of corridor passes, as the planner does", async () => {
    useStore.setState({
      points: SQUARE,
      mode: "corridor",
      params: { ...DEFAULT_PARAMS, lines: 3 },
    });
    render(<Panel />);
    await userEvent.click(step("Ajustes"));
    const field = screen.getByLabelText("Passadas");
    await userEvent.clear(field);
    await userEvent.type(field, "4");
    expect(useStore.getState().params.lines).toBe(5); // 4 would be refused by the planner
    await userEvent.clear(field);
    await userEvent.type(field, "7");
    expect(useStore.getState().params.lines).toBe(7);
    await userEvent.tab();
    expect(field).toHaveValue(7);
  });

  it("asks for the takeoff point when following terrain", async () => {
    useStore.setState({ points: SQUARE });
    render(<Panel />);
    await userEvent.click(step("Ajustes"));
    await userEvent.click(screen.getByLabelText("Acompanhar o terreno"));
    await userEvent.click(screen.getByRole("button", { name: "Marcar decolagem no mapa" }));
    expect(useStore.getState().pickingTakeoff).toBe(true);
  });

  it("offers the project's models for terrain following inside a task", async () => {
    useStore.setState({
      points: SQUARE,
      params: { ...DEFAULT_PARAMS, terrain: true },
      demSource: "dsm",
      task: {
        id: "t",
        project: 1,
        name: "Fazenda",
        extent: null,
        assets: { orthophoto: true, dsm: true, dtm: false, shots: false },
        tiles: "",
      },
    });
    render(<Panel />);
    await userEvent.click(step("Ajustes"));
    const select = screen.getByLabelText("Modelo de elevação");
    expect(select).toHaveValue("dsm");
    expect(screen.getByRole("option", { name: /DTM do projeto.*indisponível/ })).toBeDisabled();
    await userEvent.selectOptions(select, "online");
    expect(useStore.getState().demSource).toBe("online");
  });

  it("shows the saved plans only inside WebODM, once a project is open", () => {
    vi.mocked(client.insideWebodm).mockReturnValue(true);
    useStore.setState({ projectId: null });
    const { rerender } = render(<Panel />);
    expect(screen.queryByRole("region", { name: "Plano de voo" })).not.toBeInTheDocument();
    act(() => {
      useStore.setState({ projectId: 4 });
    });
    rerender(<Panel />);
    expect(screen.getByRole("region", { name: "Plano de voo" })).toBeInTheDocument();
    vi.mocked(client.insideWebodm).mockReturnValue(false);
    rerender(<Panel />);
    expect(screen.queryByRole("region", { name: "Plano de voo" })).not.toBeInTheDocument();
  });

  it("does not mention a model choice outside WebODM", async () => {
    useStore.setState({ points: SQUARE, params: { ...DEFAULT_PARAMS, terrain: true }, task: null });
    render(<Panel />);
    await userEvent.click(step("Ajustes"));
    expect(screen.queryByLabelText("Modelo de elevação")).not.toBeInTheDocument();
  });

  it("summarises the plan and exports it", async () => {
    const blob = new Blob(["zip"]);
    vi.mocked(client.exportMission).mockResolvedValue({ blob, filename: "m.zip" });
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:x"),
      revokeObjectURL: vi.fn(),
    });
    useStore.setState({ points: SQUARE, plan: PLAN, status: "ready" });
    render(<Panel />);
    await userEvent.click(step("Revisar"));
    expect(screen.getByText("1.50 km")).toBeInTheDocument();
    expect(screen.getByText("3 min 05 s · 1 bateria")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Avisos" })).toHaveTextContent(
      "altura acima do limite",
    );
    await userEvent.click(screen.getByRole("button", { name: "Baixar missão Atom 2" }));
    await waitFor(() => {
      expect(client.exportMission).toHaveBeenCalled();
    });
    vi.unstubAllGlobals();
  });

  it("offers the DJI download for a DJI drone", async () => {
    useStore.setState({
      points: SQUARE,
      plan: PLAN,
      status: "ready",
      params: { ...DEFAULT_PARAMS, drone: "mini4pro" },
    });
    render(<Panel />);
    await userEvent.click(step("Revisar"));
    expect(screen.getByRole("button", { name: "Baixar KMZ DJI" })).toBeInTheDocument();
  });

  it("shows the server's error on the review step", async () => {
    useStore.setState({ points: SQUARE, plan: null, status: "error", error: "poligono invalido" });
    render(<Panel />);
    await userEvent.click(step("Revisar"));
    expect(screen.getByRole("alert")).toHaveTextContent("poligono invalido");
  });
});
