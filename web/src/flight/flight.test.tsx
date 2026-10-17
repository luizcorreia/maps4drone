import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import type { Drone, PlanResult } from "../api/types";
import { DEFAULT_PARAMS, useStore } from "../store";
import { ElevationProfile } from "./ElevationProfile";
import { InfoCard } from "./InfoCard";
import { Legend } from "./Legend";

const drone: Drone = {
  id: "atom2",
  name: "Potensic Atom 2",
  cameras: {
    c: {
      name: "c",
      sensor_w_mm: 6.4,
      sensor_h_mm: 4.8,
      focal_mm: 4.5,
      image_w: 4000,
      image_h: 3000,
      rolling_shutter_ms: 0,
    },
  },
  default_camera: "c",
  flight_minutes: 30,
  max_speed_ms: 15,
  max_height_m: 120,
  shoot_intervals_s: [2, 3, 5],
  export_format: "atom2",
  dji_enums: null,
};

const plan = (speed: number, batteries = 1): PlanResult =>
  ({
    speed,
    interval: 2,
    warnings: [],
    stats: {
      waypoints: 3,
      distance_m: 1500,
      duration_s: 185,
      batteries,
      images: { "2": 100, "3": 70, "5": 40 },
      area_ha: 3.2,
    },
    geojson: {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: { kind: "route" },
          geometry: {
            type: "LineString",
            coordinates: [
              [0, 0],
              [0, 0.001],
              [0, 0.002],
            ],
          },
        },
        ...[80, 95, 70].map((height, index) => ({
          type: "Feature",
          properties: { kind: "waypoint", index, height },
          geometry: { type: "Point", coordinates: [0, index * 0.001] },
        })),
      ],
    },
  }) as unknown as PlanResult;

beforeEach(() => {
  useStore.setState({
    drones: [drone],
    mode: "grid",
    points: [],
    params: DEFAULT_PARAMS,
    plan: null,
    showShots: false,
    shots: null,
  });
});

describe("InfoCard", () => {
  it("renders nothing until there is a plan", () => {
    const { container } = render(<InfoCard />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the optics and the flight numbers", () => {
    useStore.setState({ plan: plan(6) });
    render(<InfoCard />);
    expect(screen.getByText("2.84")).toBeInTheDocument(); // GSD at 80 m, cm/px
    expect(screen.getByText("~100")).toBeInTheDocument(); // photos at the 2 s interval
    expect(screen.getByText("~600 MB")).toBeInTheDocument(); // 100 x 6 MB
    expect(screen.getByText("1.50")).toBeInTheDocument();
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
  });

  it("warns about motion blur and about extra batteries", () => {
    useStore.setState({ plan: plan(14, 2) });
    render(<InfoCard />);
    const notes = screen.getAllByRole("note");
    expect(notes[0]).toHaveTextContent("borrar");
    expect(notes[1]).toHaveTextContent("Mais de uma bateria");
  });

  it("collapses", async () => {
    useStore.setState({ plan: plan(6) });
    render(<InfoCard />);
    await userEvent.click(screen.getByRole("button", { name: /Dados do voo/ }));
    expect(screen.queryByText("cm/px")).not.toBeInTheDocument();
  });
});

describe("Legend", () => {
  it("lists the photos taken only while they are on the map", () => {
    useStore.setState({
      plan: plan(6),
      showShots: true,
      shots: [{ position: [0, 0], filename: null }],
    });
    const { rerender } = render(<Legend />);
    expect(screen.getByText("Foto tirada")).toBeInTheDocument();
    useStore.setState({ showShots: false });
    rerender(<Legend />);
    expect(screen.queryByText("Foto tirada")).not.toBeInTheDocument();
  });

  it("lists the takeoff marker only when there is a takeoff point", () => {
    useStore.setState({ plan: plan(6) });
    const { rerender } = render(<Legend />);
    expect(screen.queryByText("Decolagem")).not.toBeInTheDocument();
    useStore.setState({ params: { ...DEFAULT_PARAMS, takeoff: [0, 0] } });
    rerender(<Legend />);
    expect(screen.getByText("Decolagem")).toBeInTheDocument();
  });
});

describe("ElevationProfile", () => {
  it("only appears when following terrain", () => {
    useStore.setState({ plan: plan(6) });
    const { container } = render(<ElevationProfile />);
    expect(container).toBeEmptyDOMElement();
  });

  it("charts the terrain and follows the pointer", () => {
    useStore.setState({ plan: plan(6), params: { ...DEFAULT_PARAMS, terrain: true } });
    render(<ElevationProfile />);
    expect(screen.getByRole("img", { name: /Terreno e altura/ })).toBeInTheDocument();
    expect(screen.getByText(/-10 a 95 m/)).toBeInTheDocument();
    const svg = screen.getByRole("img", { name: /Terreno e altura/ });
    svg.getBoundingClientRect = () => ({ left: 0, width: 100 }) as DOMRect;
    fireEvent.pointerMove(svg, { clientX: 100 });
    expect(screen.getByRole("status")).toHaveTextContent("terreno -10 m · drone 70 m");
  });

  it("collapses", async () => {
    useStore.setState({ plan: plan(6), params: { ...DEFAULT_PARAMS, terrain: true } });
    render(<ElevationProfile />);
    await userEvent.click(screen.getByRole("button", { name: /Recolher perfil/ }));
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
