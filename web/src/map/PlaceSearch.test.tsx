import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as geocode from "../api/geocode";
import { useStore } from "../store";
import { PlaceSearch } from "./PlaceSearch";

vi.mock("../api/geocode", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/geocode")>()),
  searchPlaces: vi.fn(),
}));

const place = (label: string, south = -20.2): geocode.Place => ({
  label,
  bounds: [
    [south, -44.9],
    [south + 0.1, -44.8],
  ],
});

beforeEach(() => {
  useStore.setState({ viewTarget: null });
});

afterEach(() => {
  vi.resetAllMocks();
  vi.unstubAllGlobals();
});

describe("PlaceSearch", () => {
  it("searches only when asked, and goes straight to a single result", async () => {
    vi.mocked(geocode.searchPlaces).mockResolvedValue([place("Chácara Boa Vista")]);
    render(<PlaceSearch />);
    const search = screen.getByRole("button", { name: "Buscar" });
    expect(search).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Buscar lugar"), "chácara boa vista");
    expect(geocode.searchPlaces).not.toHaveBeenCalled(); // no search-as-you-type
    await userEvent.click(search);
    expect(geocode.searchPlaces).toHaveBeenCalledWith("chácara boa vista");
    expect(useStore.getState().viewTarget?.bounds).toEqual(place("x").bounds);
  });

  it("submits with Enter", async () => {
    vi.mocked(geocode.searchPlaces).mockResolvedValue([place("Um")]);
    render(<PlaceSearch />);
    await userEvent.type(screen.getByLabelText("Buscar lugar"), "itaúna{enter}");
    expect(geocode.searchPlaces).toHaveBeenCalledTimes(1);
  });

  it("lists several results and goes to the one picked", async () => {
    vi.mocked(geocode.searchPlaces).mockResolvedValue([
      place("Rua Sergipe, A", -20.2),
      place("Rua Sergipe, B", -19.0),
    ]);
    render(<PlaceSearch />);
    await userEvent.type(screen.getByLabelText("Buscar lugar"), "rua sergipe{enter}");
    expect(useStore.getState().viewTarget).toBeNull(); // undecided until the user picks
    await userEvent.click(await screen.findByRole("button", { name: "Rua Sergipe, B" }));
    expect(useStore.getState().viewTarget?.bounds[0][0]).toBe(-19.0);
    expect(screen.queryByRole("list", { name: "Resultados da busca" })).not.toBeInTheDocument();
  });

  it("says when nothing was found, and when the service fails", async () => {
    vi.mocked(geocode.searchPlaces).mockResolvedValueOnce([]);
    render(<PlaceSearch />);
    await userEvent.type(screen.getByLabelText("Buscar lugar"), "zzzz{enter}");
    expect(await screen.findByText(/Nenhum resultado/)).toBeInTheDocument();
    vi.mocked(geocode.searchPlaces).mockRejectedValueOnce(
      new Error("A busca de lugares falhou (429)."),
    );
    await userEvent.click(screen.getByRole("button", { name: "Buscar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("429");
  });

  it("goes to the device's position", async () => {
    vi.stubGlobal("navigator", {
      geolocation: {
        getCurrentPosition: (
          ok: (p: { coords: { latitude: number; longitude: number } }) => void,
        ) => {
          ok({ coords: { latitude: -20.15, longitude: -44.9 } });
        },
      },
    });
    render(<PlaceSearch />);
    await userEvent.click(screen.getByRole("button", { name: "Minha posição" }));
    const [[south, west], [north, east]] = useStore.getState().viewTarget?.bounds ?? [
      [0, 0],
      [0, 0],
    ];
    expect((south + north) / 2).toBeCloseTo(-20.15, 6);
    expect((west + east) / 2).toBeCloseTo(-44.9, 6);
  });

  it("explains a refused location", async () => {
    vi.stubGlobal("navigator", {
      geolocation: {
        getCurrentPosition: (_ok: unknown, fail: () => void) => {
          fail();
        },
      },
    });
    render(<PlaceSearch />);
    await userEvent.click(screen.getByRole("button", { name: "Minha posição" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível obter a sua posição",
    );
  });

  it("repeating the same place moves the map again", () => {
    useStore.getState().showBounds(place("x").bounds);
    const first = useStore.getState().viewTarget?.seq ?? 0;
    useStore.getState().showBounds(place("x").bounds);
    expect(useStore.getState().viewTarget?.seq).toBe(first + 1);
  });
});
