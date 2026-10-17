import { describe, expect, it } from "vitest";

import type { Camera, PlanResult } from "../api/types";
import { DEFAULT_PARAMS } from "../store";
import {
  blurAdvice,
  blurSpeedLimit,
  elevationProfile,
  footprintM,
  formatDuration,
  formatStorage,
  gsdM,
  haversineM,
  lineSpacingM,
  photoSizeMb,
  shotDistanceM,
  subjectDistance,
} from "./metrics";

const atom2: Camera = {
  name: "wide-26mm-12mp",
  sensor_w_mm: 6.4,
  sensor_h_mm: 4.8,
  focal_mm: 4.5,
  image_w: 4000,
  image_h: 3000,
  rolling_shutter_ms: 0,
};

describe("optics", () => {
  it("computes the Atom 2 GSD like the Python core", () => {
    // 6.4 * 100 / (4.5 * 4000) = 0.03556 m/px
    expect(gsdM(atom2, 100)).toBeCloseTo(0.035556, 5);
  });

  it("derives footprint, line spacing and shot distance", () => {
    const [w, h] = footprintM(atom2, 100);
    expect(w).toBeCloseTo(142.22, 2);
    expect(h).toBeCloseTo(106.67, 2);
    expect(lineSpacingM(atom2, 100, 70)).toBeCloseTo(w * 0.3, 6);
    expect(shotDistanceM(atom2, 100, 80)).toBeCloseTo(h * 0.2, 6);
  });

  it("estimates the storage of a photo and formats it", () => {
    expect(photoSizeMb(atom2)).toBe(6);
    expect(formatStorage(950)).toBe("950 MB");
    expect(formatStorage(2400)).toBe("2.4 GB");
  });

  it("measures the subject distance per mode", () => {
    expect(subjectDistance("grid", DEFAULT_PARAMS)).toBe(80);
    expect(subjectDistance("facade", { ...DEFAULT_PARAMS, standoff: 12 })).toBe(12);
    expect(
      subjectDistance("orbit", { ...DEFAULT_PARAMS, radius: 30, altitude: 40, target_height: 0 }),
    ).toBe(50);
  });
});

describe("formatting and distance", () => {
  it("formats durations", () => {
    expect(formatDuration(185)).toBe("3 min 05 s");
  });

  it("computes great-circle distance", () => {
    // one degree of latitude is about 111.2 km
    expect(haversineM([0, 0], [1, 0])).toBeCloseTo(111_195, -2);
    expect(haversineM([10, 20], [10, 20])).toBe(0);
  });
});

const plan = (speed: number): PlanResult =>
  ({
    speed,
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

describe("elevationProfile", () => {
  it("derives the ground from the drone height and the altitude", () => {
    const profile = elevationProfile(plan(5), 80);
    expect(profile.map((p) => p.drone)).toEqual([80, 95, 70]);
    expect(profile.map((p) => p.ground)).toEqual([0, 15, -10]);
    expect(profile[0]?.distance).toBe(0);
    expect(profile[2]?.distance).toBeCloseTo(222.4, 0);
  });
});

describe("blurAdvice", () => {
  it("stays quiet within the limit and warns beyond it", () => {
    const limit = blurSpeedLimit(gsdM(atom2, 80));
    expect(limit).toBeCloseTo(9.95, 1);
    expect(blurAdvice(plan(limit - 0.1), atom2, 80)).toBeNull();
    expect(blurAdvice(plan(limit + 1), atom2, 80)?.text).toContain("borrar");
  });
});
