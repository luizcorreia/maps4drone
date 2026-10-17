import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";
import * as client from "../api/client";
import type { TaskContext } from "../api/types";
import { useStore } from "../store";
import { hasMap, TaskPicker } from "./TaskPicker";

vi.mock("../api/client");

const TASK: TaskContext = {
  id: "t1",
  project: 1,
  name: "Rua Sergipe",
  extent: null,
  assets: { orthophoto: true, dsm: true, dtm: false },
  tiles: "",
};

beforeEach(() => {
  vi.mocked(client.insideWebodm).mockReturnValue(true);
  vi.mocked(client.fetchDrones).mockResolvedValue([]);
  vi.mocked(client.fetchProjects).mockResolvedValue([
    { id: 1, name: "Primeiro projeto", tasks: ["t1"] },
    { id: 2, name: "Vazio", tasks: [] },
  ]);
  vi.mocked(client.fetchProjectTasks).mockImplementation((id) =>
    Promise.resolve(
      id === 1
        ? [
            {
              id: "t1",
              name: "Rua Sergipe",
              status: 40,
              available_assets: ["orthophoto.tif", "dsm.tif"],
            },
            { id: "t2", name: "Em andamento", status: 20, available_assets: [] },
            { id: "t3", name: "Só nuvem de pontos", status: 40, available_assets: ["all.zip"] },
          ]
        : [],
    ),
  );
  vi.mocked(client.fetchTask).mockResolvedValue(TASK);
  vi.mocked(client.fetchPlans).mockResolvedValue([]);
  useStore.setState({
    task: null,
    demSource: "online",
    points: [],
    status: "idle",
    error: null,
    projectId: null,
    plans: [],
    planId: null,
    planName: "",
    savedSnapshot: null,
    plansError: null,
  });
  window.history.replaceState(null, "", "/plugins/maps4drone/index.html");
});

afterEach(() => {
  vi.resetAllMocks();
});

describe("hasMap", () => {
  it("wants a completed task with an orthophoto, DSM or DTM", () => {
    expect(hasMap({ id: "a", name: "a", status: 40, available_assets: ["dtm.tif"] })).toBe(true);
    expect(hasMap({ id: "a", name: "a", status: 20, available_assets: ["dtm.tif"] })).toBe(false);
    expect(hasMap({ id: "a", name: "a", status: 40, available_assets: ["all.zip"] })).toBe(false);
    expect(hasMap({ id: "a", name: "a", status: 40, available_assets: null })).toBe(false);
  });
});

describe("TaskPicker", () => {
  it("lists the user's projects and, for one, only its tasks with a map", async () => {
    render(<TaskPicker />);
    await screen.findByRole("option", { name: "Primeiro projeto" });
    await userEvent.selectOptions(screen.getByLabelText("Projeto do WebODM"), "1");
    expect(await screen.findByRole("option", { name: "Rua Sergipe" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Em andamento" })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Só nuvem de pontos" })).not.toBeInTheDocument();
  });

  it("opens the chosen task and records it in the address", async () => {
    render(<TaskPicker />);
    await screen.findByRole("option", { name: "Primeiro projeto" });
    await userEvent.selectOptions(screen.getByLabelText("Projeto do WebODM"), "1");
    await userEvent.selectOptions(await screen.findByLabelText("Tarefa do projeto"), "t1");
    expect(client.fetchTask).toHaveBeenCalledWith("t1");
    expect(window.location.search).toBe("?project=1&task=t1");
    expect(client.fetchPlans).toHaveBeenCalledWith(1); // the project's plans come along
  });

  it("says when a project has nothing to plan over", async () => {
    render(<TaskPicker />);
    await screen.findByRole("option", { name: "Vazio" });
    await userEvent.selectOptions(screen.getByLabelText("Projeto do WebODM"), "2");
    expect(
      await screen.findByRole("option", { name: "Nenhuma tarefa com mapa" }),
    ).toBeInTheDocument();
  });

  it("leaves the task for the public maps", async () => {
    useStore.setState({ task: TASK, projectId: 1 });
    window.history.replaceState(null, "", "/plugins/maps4drone/index.html?project=1&task=t1");
    render(<TaskPicker />);
    await screen.findByRole("option", { name: "Primeiro projeto" });
    expect(screen.getByLabelText("Projeto do WebODM")).toHaveValue("1"); // follows the open task
    await userEvent.selectOptions(screen.getByLabelText("Projeto do WebODM"), "");
    expect(useStore.getState()).toMatchObject({ task: null, projectId: null });
    expect(window.location.search).toBe("");
  });
});

describe("a task of another project", () => {
  it("is dropped when the project changes, keeping the new project in the address", async () => {
    useStore.setState({ task: TASK, projectId: 1 });
    window.history.replaceState(null, "", "/plugins/maps4drone/index.html?project=1&task=t1");
    render(<TaskPicker />);
    await screen.findByRole("option", { name: "Vazio" });
    await userEvent.selectOptions(screen.getByLabelText("Projeto do WebODM"), "2");
    expect(useStore.getState()).toMatchObject({ task: null, projectId: 2 });
    expect(window.location.search).toBe("?project=2");
  });
});

describe("App inside WebODM", () => {
  it("reopens the project named in the address, without a task", () => {
    window.history.replaceState(null, "", "/plugins/maps4drone/index.html?project=4");
    render(<App />);
    expect(client.fetchPlans).toHaveBeenCalledWith(4);
    expect(client.fetchTask).not.toHaveBeenCalled();
  });

  it("links back to the dashboard, and to the project once a task is open", async () => {
    render(<App />);
    expect(screen.getByRole("link", { name: /WebODM/ })).toHaveAttribute("href", "/dashboard/");
    useStore.setState({ task: TASK });
    await waitFor(() => {
      expect(screen.getByRole("link", { name: /WebODM/ })).toHaveAttribute(
        "href",
        "/dashboard/?project_id=1",
      );
    });
  });

  it("has no WebODM controls in the standalone app", () => {
    vi.mocked(client.insideWebodm).mockReturnValue(false);
    render(<App />);
    expect(screen.queryByRole("link", { name: /WebODM/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Projeto do WebODM")).not.toBeInTheDocument();
  });
});
