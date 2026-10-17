import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import type { LngLat, SavedPlan } from "../api/types";
import { DEFAULT_PARAMS, useStore } from "../store";
import { PlanBar } from "./PlanBar";

vi.mock("../api/client");

const SQUARE: LngLat[] = [
  [-51.9, -23.15],
  [-51.89, -23.15],
  [-51.89, -23.14],
];

const plan = (over: Partial<SavedPlan> = {}): SavedPlan => ({
  id: "p1",
  name: "Norte",
  request: {
    mode: "grid",
    geometry: { type: "Polygon", coordinates: [[...SQUARE, SQUARE[0] as LngLat]] },
    params: DEFAULT_PARAMS,
  },
  status: "planned",
  task_id: null,
  created_at: "t",
  created_by: "ana",
  updated_at: "t",
  updated_by: "ana",
  ...over,
});

beforeEach(() => {
  vi.mocked(client.planMission).mockResolvedValue({} as never);
  useStore.setState({
    drones: [],
    mode: "grid",
    points: [],
    params: DEFAULT_PARAMS,
    task: null,
    projectId: 4,
    plans: [],
    planId: null,
    planName: "",
    savedSnapshot: null,
    plansError: null,
    plansBusy: false,
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.resetAllMocks();
});

describe("PlanBar", () => {
  it("saves only with a name and a drawn area", async () => {
    render(<PlanBar />);
    const save = screen.getByRole("button", { name: "Salvar" });
    expect(save).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Nome do plano"), "Norte");
    expect(save).toBeDisabled(); // named, but nothing drawn
    useStore.setState({ points: SQUARE });
    await vi.waitFor(() => {
      expect(save).toBeEnabled();
    });
    expect(screen.getByRole("status")).toHaveTextContent("alterações não salvas");
  });

  it("saves, then shows the plan as saved and lists it", async () => {
    vi.mocked(client.savePlan).mockResolvedValue(plan());
    useStore.setState({ points: SQUARE });
    render(<PlanBar />);
    await userEvent.type(screen.getByLabelText("Nome do plano"), "Norte");
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(client.savePlan).toHaveBeenCalledWith(4, expect.objectContaining({ name: "Norte" }));
    expect(await screen.findByText("✓ salvo")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Norte · planejado" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Salvar" })).toBeDisabled(); // nothing new to save
  });

  it("opens a saved plan from the list", async () => {
    useStore.setState({ plans: [plan(), plan({ id: "p2", name: "Sul", status: "flown" })] });
    render(<PlanBar />);
    expect(screen.getByRole("option", { name: "Sul · realizado" })).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Abrir plano salvo"), "p1");
    expect(useStore.getState()).toMatchObject({ planId: "p1", planName: "Norte", points: SQUARE });
    expect(screen.getByLabelText("Nome do plano")).toHaveValue("Norte");
  });

  it("asks before throwing away unsaved work", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    useStore.setState({ plans: [plan()], points: SQUARE }); // drawn but never saved
    render(<PlanBar />);
    await userEvent.selectOptions(screen.getByLabelText("Abrir plano salvo"), "p1");
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("Descartar"));
    expect(useStore.getState().planId).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Novo" }));
    expect(useStore.getState().points).toEqual(SQUARE); // refused: still there
    confirm.mockReturnValue(true);
    await userEvent.click(screen.getByRole("button", { name: "Novo" }));
    expect(useStore.getState().points).toEqual([]);
  });

  it("does not ask when there is nothing to lose", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<PlanBar />);
    await userEvent.click(screen.getByRole("button", { name: "Novo" }));
    expect(confirm).not.toHaveBeenCalled();
  });

  it("duplicates and deletes only an open plan, the latter after confirming", async () => {
    vi.mocked(client.deletePlan).mockResolvedValue(undefined);
    useStore.setState({ plans: [plan()] });
    render(<PlanBar />);
    expect(screen.getByRole("button", { name: "Duplicar" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Apagar" })).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Abrir plano salvo"), "p1");
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    await userEvent.click(screen.getByRole("button", { name: "Apagar" }));
    expect(client.deletePlan).not.toHaveBeenCalled();
    confirm.mockReturnValue(true);
    await userEvent.click(screen.getByRole("button", { name: "Apagar" }));
    expect(client.deletePlan).toHaveBeenCalledWith(4, "p1");
  });

  it("shows what went wrong", () => {
    useStore.setState({ plansError: "o projeto ja tem 200 planos" });
    render(<PlanBar />);
    expect(screen.getByRole("alert")).toHaveTextContent("200 planos");
  });
});
