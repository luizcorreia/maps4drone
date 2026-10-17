import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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
  });
});

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

  it("switches the basemap", async () => {
    render(<MapView />);
    const satellite = screen.getByRole("button", { name: "Satélite" });
    await userEvent.click(satellite);
    expect(satellite).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Mapa" })).toHaveAttribute("aria-pressed", "false");
  });
});
