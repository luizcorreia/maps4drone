import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "../api/client";
import type { PlanResult, SavedPlan, TaskContext } from "../api/types";
import { DEFAULT_PARAMS, useStore } from "../store";
import { AfterFlight } from "./AfterFlight";

vi.mock("../api/client");

const TASK: TaskContext = {
  id: "t1",
  project: 4,
  name: "Voo de outubro",
  extent: null,
  assets: { orthophoto: true, dsm: true, dtm: false, shots: true },
  tiles: "",
};

const plan = (over: Partial<SavedPlan> = {}): SavedPlan => ({
  id: "p1",
  name: "Norte",
  request: { mode: "grid", geometry: null, params: DEFAULT_PARAMS },
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
    projectId: 4,
    task: null,
    plans: [],
    planId: null,
    plansBusy: false,
    plansError: null,
    plan: null,
    shots: null,
    showShots: false,
    shotsError: null,
    points: [],
  });
  window.history.replaceState(null, "", "/plugins/maps4drone/index.html");
});

afterEach(() => {
  vi.resetAllMocks();
});

describe("AfterFlight", () => {
  it("has nothing to say before there is a plan or a task", () => {
    const { container } = render(<AfterFlight />);
    expect(container).toBeEmptyDOMElement();
  });

  it("asks for the processed task when a plan has none open", () => {
    useStore.setState({ plans: [plan()], planId: "p1" });
    render(<AfterFlight />);
    expect(screen.getByText(/Abra a tarefa processada/)).toBeInTheDocument();
  });

  it("ties the open plan to the open task of the same project", async () => {
    vi.mocked(client.linkPlanTask).mockResolvedValue(plan({ task_id: "t1", status: "flown" }));
    useStore.setState({ plans: [plan()], planId: "p1", task: TASK });
    render(<AfterFlight />);
    await userEvent.click(
      screen.getByRole("button", { name: /Vincular à tarefa «Voo de outubro»/ }),
    );
    expect(client.linkPlanTask).toHaveBeenCalledWith(4, "p1", "t1");
    expect(await screen.findByText("✓ Realizado nesta tarefa")).toBeInTheDocument();
    expect(useStore.getState().plans[0]?.status).toBe("flown");
  });

  it("unties a plan from the task it was flown on", async () => {
    vi.mocked(client.linkPlanTask).mockResolvedValue(plan());
    useStore.setState({
      plans: [plan({ task_id: "t1", status: "flown" })],
      planId: "p1",
      task: TASK,
    });
    render(<AfterFlight />);
    await userEvent.click(screen.getByRole("button", { name: "Desvincular" }));
    expect(client.linkPlanTask).toHaveBeenCalledWith(4, "p1", null);
    expect(await screen.findByRole("button", { name: /Vincular à tarefa/ })).toBeInTheDocument();
  });

  it("opens the task a plan was flown on, from another one", async () => {
    vi.mocked(client.fetchTask).mockResolvedValue({ ...TASK, id: "t9" });
    vi.mocked(client.fetchPlans).mockResolvedValue([]);
    useStore.setState({
      plans: [plan({ task_id: "t9", status: "flown" })],
      planId: "p1",
      task: TASK,
    });
    render(<AfterFlight />);
    expect(screen.getByText("Realizado em outra tarefa")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Abrir a tarefa" }));
    expect(client.fetchTask).toHaveBeenCalledWith("t9");
    expect(window.location.search).toBe("?project=4&task=t9");
  });

  it("does not offer a task of another project", () => {
    useStore.setState({ plans: [plan()], planId: "p1", task: { ...TASK, project: 1 } });
    render(<AfterFlight />);
    expect(screen.queryByRole("button", { name: /Vincular/ })).not.toBeInTheDocument();
  });

  it("shows where the photos were taken, against how many were planned", async () => {
    vi.mocked(client.fetchShots).mockResolvedValue([
      { position: [-44.9, -20.1], filename: "A.JPG" },
      { position: [-44.8, -20.1], filename: "B.JPG" },
      { position: [-44.7, -20.1], filename: null },
    ]);
    useStore.setState({
      task: TASK,
      plan: { interval: 2, stats: { images: { "2": 71 } } } as unknown as PlanResult,
    });
    render(<AfterFlight />);
    await userEvent.click(screen.getByLabelText(/Mostrar onde as fotos foram tiradas/));
    expect(client.fetchShots).toHaveBeenCalledWith(4, "t1");
    expect(await screen.findByText("(3 tiradas · 71 planejadas)")).toBeInTheDocument();
    expect(useStore.getState().showShots).toBe(true);
    await userEvent.click(screen.getByLabelText(/Mostrar onde as fotos foram tiradas/));
    expect(useStore.getState().showShots).toBe(false);
    await userEvent.click(screen.getByLabelText(/Mostrar onde as fotos foram tiradas/));
    expect(client.fetchShots).toHaveBeenCalledTimes(1); // asked once, kept
  });

  it("offers no photo positions for a task that has none, and says when they fail", async () => {
    useStore.setState({ task: { ...TASK, assets: { ...TASK.assets, shots: false } } });
    const { rerender } = render(<AfterFlight />);
    expect(screen.queryByLabelText(/Mostrar onde as fotos/)).not.toBeInTheDocument();
    vi.mocked(client.fetchShots).mockRejectedValue(new Error("Erro 404"));
    useStore.setState({ task: TASK });
    rerender(<AfterFlight />);
    await userEvent.click(screen.getByLabelText(/Mostrar onde as fotos foram tiradas/));
    expect(await screen.findByRole("alert")).toHaveTextContent("Erro 404");
    expect(useStore.getState().showShots).toBe(false);
  });

  it("forgets the photo positions when another task is opened", async () => {
    vi.mocked(client.fetchTask).mockResolvedValue({ ...TASK, id: "t2" });
    vi.mocked(client.fetchPlans).mockResolvedValue([]);
    useStore.setState({
      task: TASK,
      shots: [{ position: [0, 0], filename: null }],
      showShots: true,
    });
    await useStore.getState().loadTask("t2");
    expect(useStore.getState()).toMatchObject({ shots: null, showShots: false });
  });
});
