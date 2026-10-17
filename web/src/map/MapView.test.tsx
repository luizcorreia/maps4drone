import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import { DEFAULT_PARAMS, useStore } from "../store";
import { MapView } from "./MapView";

afterEach(() => {
  vi.restoreAllMocks();
});

beforeEach(() => {
  useStore.setState({
    mode: "grid",
    points: [],
    params: DEFAULT_PARAMS,
    plan: null,
    pickingTakeoff: false,
    status: "idle",
    error: null,
    task: null,
  });
});

vi.mock("../api/client");

describe("MapView", () => {
  it("guides the user through the points the mode needs", () => {
    render(<MapView />);
    expect(screen.getByRole("status")).toHaveTextContent("a área de voo (0/3 pontos)");
    act(() => {
      useStore.setState({ mode: "orbit" });
    });
    expect(screen.getByRole("status")).toHaveTextContent("o centro da órbita");
  });

  it("shows a planning error on the map", () => {
    // jsdom has no canvas, which Leaflet's vector layers draw on
    const noop = new Proxy({}, { get: () => () => undefined });
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(noop as never);
    useStore.setState({
      points: [
        [-51.9, -23.15],
        [-51.89, -23.15],
        [-51.89, -23.14],
      ],
      status: "error",
      error: "a area e pequena demais",
    });
    render(<MapView />);
    expect(screen.getByRole("status")).toHaveTextContent("a area e pequena demais");
    expect(screen.getByRole("status")).toHaveClass("map-hint-error");
  });

  it("asks for the takeoff point while picking", () => {
    render(<MapView />);
    act(() => {
      useStore.getState().setPickingTakeoff(true);
    });
    expect(screen.getByRole("status")).toHaveTextContent("ponto de decolagem");
  });

  it("renders a pin per drawn point", () => {
    useStore.setState({
      points: [
        [-51.9, -23.15],
        [-51.89, -23.15],
      ],
    });
    const { container } = render(<MapView />);
    expect(container.querySelectorAll(".pin-draw")).toHaveLength(2);
  });

  it("opens on the project's orthophoto when a task has one", () => {
    useStore.setState({
      task: {
        id: "t",
        project: 1,
        name: "Fazenda",
        extent: null,
        assets: { orthophoto: true, dsm: true, dtm: false },
        tiles: "/api/projects/1/tasks/t/orthophoto/tiles/{z}/{x}/{y}.png",
      },
    });
    render(<MapView />);
    expect(screen.getByRole("button", { name: "Ortofoto" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    act(() => {
      useStore.setState({ task: null });
    });
    expect(screen.queryByRole("button", { name: "Ortofoto" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mapa" })).toHaveAttribute("aria-pressed", "true");
  });

  it("opens on the satellite inside WebODM when the project has no orthophoto yet", () => {
    vi.mocked(client.insideWebodm).mockReturnValue(true);
    render(<MapView />);
    expect(screen.getByRole("button", { name: "Satélite" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("keeps the street map as the default of the standalone app", () => {
    vi.mocked(client.insideWebodm).mockReturnValue(false);
    render(<MapView />);
    expect(screen.getByRole("button", { name: "Mapa" })).toHaveAttribute("aria-pressed", "true");
  });

  it("switches the basemap", async () => {
    render(<MapView />);
    const satellite = screen.getByRole("button", { name: "Satélite" });
    await userEvent.click(satellite);
    expect(satellite).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Mapa" })).toHaveAttribute("aria-pressed", "false");
  });
});
