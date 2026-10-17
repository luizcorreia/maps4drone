import type { Drone, ImportResult, MissionFile, PlanRequest, PlanResult } from "./types";

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

function post(path: string, body: BodyInit, headers: HeadersInit, signal?: AbortSignal) {
  return request(path, { method: "POST", body, headers, signal });
}

const json = (body: unknown) => ({
  body: JSON.stringify(body),
  headers: { "Content-Type": "application/json" },
});

export async function fetchDrones(signal?: AbortSignal): Promise<Drone[]> {
  return (await (await request("/api/drones", { signal })).json()) as Drone[];
}

export async function planMission(req: PlanRequest, signal?: AbortSignal): Promise<PlanResult> {
  const { body, headers } = json(req);
  return (await (await post("/api/plan", body, headers, signal)).json()) as PlanResult;
}

export async function exportMission(req: PlanRequest, signal?: AbortSignal): Promise<MissionFile> {
  const { body, headers } = json(req);
  const res = await post("/api/export", body, headers, signal);
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? "missao.zip";
  return { blob: await res.blob(), filename };
}

export async function importFile(file: File, signal?: AbortSignal): Promise<ImportResult> {
  const res = await post(
    `/api/import?name=${encodeURIComponent(file.name)}`,
    file,
    { "Content-Type": "application/octet-stream" },
    signal,
  );
  return (await res.json()) as ImportResult;
}
