import { afterEach, describe, expect, it, vi } from "vitest";

import { searchPlaces, toPlace } from "./geocode";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("toPlace", () => {
  it("turns Nominatim's [south, north, west, east] strings into a box", () => {
    const place = toPlace({
      display_name: "Itaúna, Minas Gerais, Brasil",
      lat: "-20.07",
      lon: "-44.58",
      boundingbox: ["-20.2", "-19.9", "-44.8", "-44.4"],
    });
    expect(place).toEqual({
      label: "Itaúna, Minas Gerais, Brasil",
      bounds: [
        [-20.2, -44.8],
        [-19.9, -44.4],
      ],
    });
  });

  it("gives a point-like hit (a house) a neighbourhood to look at", () => {
    const place = toPlace({ display_name: "Rua Sergipe 100", lat: "-20.1466", lon: "-44.8977" });
    const [[south, west], [north, east]] = place?.bounds ?? [
      [0, 0],
      [0, 0],
    ];
    expect(north - south).toBeCloseTo(0.002, 6);
    expect(east - west).toBeCloseTo(0.002, 6);
    expect((south + north) / 2).toBeCloseTo(-20.1466, 6);
  });

  it("drops a hit without a name or a position", () => {
    expect(toPlace({ lat: "1", lon: "2" })).toBeNull();
    expect(toPlace({ display_name: "Nowhere" })).toBeNull();
    expect(toPlace({ display_name: "Odd", lat: "x", lon: "y" })).toBeNull();
  });
});

describe("searchPlaces with a comma-separated address", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("tries again as plain words, a second later, when the commas find nothing", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response("[]"))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify([{ display_name: "Rua Sergipe, Itaúna", lat: "-20.1", lon: "-44.9" }]),
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    const result = searchPlaces("Rua Sergipe, Itaúna, Minas Gerais");
    await vi.advanceTimersByTimeAsync(500);
    expect(fetchMock).toHaveBeenCalledTimes(1); // respects the one-request-per-second policy
    await vi.advanceTimersByTimeAsync(700);
    expect((await result).map((p) => p.label)).toEqual(["Rua Sergipe, Itaúna"]);
    const retried = new URL((fetchMock.mock.calls[1] as [URL])[0]);
    expect(retried.searchParams.get("q")).toBe("Rua Sergipe Itaúna Minas Gerais");
  });

  it("does not retry a query that has no commas, nor one that already found something", async () => {
    const empty = vi.fn().mockResolvedValue(new Response("[]"));
    vi.stubGlobal("fetch", empty);
    expect(await searchPlaces("zzzz")).toEqual([]);
    expect(empty).toHaveBeenCalledTimes(1);
    const found = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify([{ display_name: "A", lat: "1", lon: "2" }])));
    vi.stubGlobal("fetch", found);
    expect(await searchPlaces("a, b")).toHaveLength(1);
    expect(found).toHaveBeenCalledTimes(1);
  });
});

describe("searchPlaces", () => {
  it("asks Nominatim in Portuguese for a few results and keeps the usable ones", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify([
          { display_name: "Chácara A", lat: "-20.1", lon: "-44.9" },
          { lat: "0", lon: "0" },
        ]),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const places = await searchPlaces("chácara boa vista");
    expect(places.map((p) => p.label)).toEqual(["Chácara A"]);
    const url = new URL((fetchMock.mock.calls[0] as [URL])[0]);
    expect(url.origin + url.pathname).toBe("https://nominatim.openstreetmap.org/search");
    expect(Object.fromEntries(url.searchParams)).toMatchObject({
      q: "chácara boa vista",
      limit: "5",
      "accept-language": "pt-BR",
    });
  });

  it("reports a failing service", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 429 })));
    await expect(searchPlaces("x")).rejects.toThrow("429");
  });
});
