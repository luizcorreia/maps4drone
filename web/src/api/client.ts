import type {
  Drone,
  ImportResult,
  MissionFile,
  PlanRequest,
  PlanResult,
  TaskContext,
  WebodmProject,
  WebodmTask,
} from "./types";

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

interface ValidationIssue {
  loc?: (string | number)[];
  msg?: string;
}

/** The API answers {"detail": "msg"}, or a list of issues for request validation errors. */
function detailMessage(body: unknown): string | null {
  if (typeof body !== "object" || body === null || !("detail" in body)) return null;
  const { detail } = body;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return (detail as ValidationIssue[])
      .map((i) => `${i.loc?.slice(1).join(".") ?? "?"}: ${i.msg ?? "valor inválido"}`)
      .join("; ");
  }
  return null;
}

/** `/api` on its own server; the WebODM build points this at the plugin's API. */
export function apiBase(): string {
  return (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api";
}

/** Django refuses session-authenticated writes without its CSRF token. */
function csrfHeaders(): Record<string, string> {
  const token = /(?:^|;\s*)csrftoken=([^;]+)/.exec(document.cookie)?.[1];
  return token ? { "X-CSRFToken": decodeURIComponent(token) } : {};
}

async function request(path: string, init: RequestInit): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError("Não foi possível falar com o servidor.", 0);
  }
  if (res.ok) return res;
  const body: unknown = await res.json().catch(() => null);
  throw new ApiError(detailMessage(body) ?? `Erro ${res.status.toString()}`, res.status);
}

function post(path: string, body: BodyInit, headers: Record<string, string>, signal?: AbortSignal) {
  return request(path, { method: "POST", body, headers: { ...csrfHeaders(), ...headers }, signal });
}

const json = (body: unknown) => ({
  body: JSON.stringify(body),
  headers: { "Content-Type": "application/json" },
});

interface CallOptions {
  /** Plan against this WebODM task, so its DSM/DTM can be used. */
  taskId?: string | null;
  signal?: AbortSignal;
}

const route = (path: string, taskId?: string | null) =>
  taskId ? `${apiBase()}/task/${encodeURIComponent(taskId)}${path}` : `${apiBase()}${path}`;

export async function fetchDrones(signal?: AbortSignal): Promise<Drone[]> {
  return (await (await request(`${apiBase()}/drones`, { signal })).json()) as Drone[];
}

export async function fetchTask(taskId: string, signal?: AbortSignal): Promise<TaskContext> {
  return (await (await request(route("/info", taskId), { signal })).json()) as TaskContext;
}

export async function planMission(
  req: PlanRequest,
  options: CallOptions = {},
): Promise<PlanResult> {
  const { body, headers } = json(req);
  const res = await post(route("/plan", options.taskId), body, headers, options.signal);
  return (await res.json()) as PlanResult;
}

export async function exportMission(
  req: PlanRequest,
  options: CallOptions = {},
): Promise<MissionFile> {
  const { body, headers } = json(req);
  const res = await post(route("/export", options.taskId), body, headers, options.signal);
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? "missao.zip";
  return { blob: await res.blob(), filename };
}

export async function importFile(file: File, signal?: AbortSignal): Promise<ImportResult> {
  const res = await post(
    `${apiBase()}/import?name=${encodeURIComponent(file.name)}`,
    file,
    { "Content-Type": "application/octet-stream" },
    signal,
  );
  return (await res.json()) as ImportResult;
}

/** True when the page is the WebODM plugin's, so WebODM's own API is there to talk to. */
export const insideWebodm = (): boolean => import.meta.env.VITE_WEBODM === "true";

export async function fetchProjects(signal?: AbortSignal): Promise<WebodmProject[]> {
  return (await (await request("/api/projects/", { signal })).json()) as WebodmProject[];
}

export async function fetchProjectTasks(
  projectId: number,
  signal?: AbortSignal,
): Promise<WebodmTask[]> {
  return (await (
    await request(`/api/projects/${projectId.toString()}/tasks/`, { signal })
  ).json()) as WebodmTask[];
}
