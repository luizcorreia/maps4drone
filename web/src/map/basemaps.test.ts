import { describe, expect, it } from "vitest";

import { projectBasemap } from "./basemaps";

describe("projectBasemap", () => {
  it("keeps the tile requests inside the task's extent, as [[south, west], [north, east]]", () => {
    const [layer] = projectBasemap(
      "/tiles/{z}/{x}/{y}.png",
      [-44.9, -20.15, -44.89, -20.14],
    ).layers;
    expect(layer?.bounds).toEqual([
      [-20.15, -44.9],
      [-20.14, -44.89],
    ]);
  });

  it("asks for no bounds when the extent is unknown", () => {
    const [layer] = projectBasemap("/tiles/{z}/{x}/{y}.png", null).layers;
    expect(layer).not.toHaveProperty("bounds");
  });
});
