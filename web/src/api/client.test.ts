import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, exportMission, fetchDrones, importFile, planMission } from "./client";
import { toGeometry } from "./geometry";
import { DEFAULT_PARAMS } from "../store";

const reply = (body: BodyInit | null, init?: ResponseInit) => new Response(body, init);

function stubFetch(response: Response) {
  const fetchMock = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

const request = {
  mode: "grid" as const,
  geometry: toGeometry("grid", [
    [0, 0],
    [1, 0],
    [1, 1],
  ]),
  params: DEFAULT_PARAMS,
};

describe("errors", () => {
  it("uses the detail string from the server", async () => {
    stubFetch(
      reply(JSON.stringify({ detail: "desenhe a geometria no mapa" }), {
        status: 422,
      }),
    );
    await expect(planMission(request)).rejects.toMatchObject({
      message: "desenhe a geometria no mapa",
      status: 422,
    });
  });

  it("flattens request validation issues", async () => {
    const detail = [{ loc: ["body", "params", "front"], msg: "less than 100" }];
    stubFetch(reply(JSON.stringify({ detail }), { status: 422 }));
    await expect(planMission(request)).rejects.toThrow("params.front: less than 100");
  });

  it("explains an unreachable server", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));
    await expect(fetchDrones()).rejects.toBeInstanceOf(ApiError);
    await expect(fetchDrones()).rejects.toThrow("Não foi possível falar com o servidor");
  });

  it("falls back to the status when the body is not JSON", async () => {
    stubFetch(reply("boom", { status: 500 }));
    await expect(fetchDrones()).rejects.toThrow("Erro 500");
  });
});

describe("requests", () => {
  it("posts the plan request as JSON", async () => {
    const fetchMock = stubFetch(reply(JSON.stringify({ stats: {} })));
    await planMission(request);
    const [path, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/plan");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toMatchObject({ mode: "grid" });
  });

  it("reads the file name from Content-Disposition on export", async () => {
    stubFetch(
      reply("zip", {
        headers: {
          "Content-Disposition": 'attachment; filename="maps4drone-1.kmz"',
        },
      }),
    );
    const file = await exportMission(request);
    expect(file.filename).toBe("maps4drone-1.kmz");
  });

  it("sends the raw file with its encoded name on import", async () => {
    const fetchMock = stubFetch(reply(JSON.stringify({ polygon: null, line: null })));
    await importFile(new File(["x"], "área 1.kml"));
    expect((fetchMock.mock.calls[0] as [string])[0]).toBe("/api/import?name=%C3%A1rea%201.kml");
  });
});
