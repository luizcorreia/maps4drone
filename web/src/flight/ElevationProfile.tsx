import { useMemo, useState } from "react";

import { useStore } from "../store";
import { elevationProfile, type ProfilePoint } from "./metrics";

const W = 1000;
const H = 150;
const PAD = 8;

function scale(points: readonly ProfilePoint[]) {
  const values = points.flatMap((p) => [p.ground, p.drone, 0]);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = Math.max(high - low, 1);
  const total = Math.max(points[points.length - 1]?.distance ?? 1, 1);
  return {
    low,
    high,
    total,
    x: (distance: number) => (distance / total) * W,
    y: (value: number) => H - PAD - ((value - low) / span) * (H - 2 * PAD),
  };
}

/** Terrain against the drone's path, relative to the takeoff point. Shown with terrain following. */
export function ElevationProfile() {
  const plan = useStore((s) => s.plan);
  const terrain = useStore((s) => s.params.terrain);
  const altitude = useStore((s) => s.params.altitude);
  const [open, setOpen] = useState(true);
  const [hover, setHover] = useState<number | null>(null);

  const profile = useMemo(
    () => (plan && terrain ? elevationProfile(plan, altitude) : []),
    [plan, terrain, altitude],
  );
  if (profile.length < 2) return null;

  const { low, high, total, x, y } = scale(profile);
  const line = (pick: (p: ProfilePoint) => number) =>
    profile
      .map((p, i) => `${i === 0 ? "M" : "L"}${x(p.distance).toFixed(1)},${y(pick(p)).toFixed(1)}`)
      .join(" ");
  const ground = line((p) => p.ground);
  const active = hover === null ? null : profile[hover];

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const distance = ((e.clientX - rect.left) / rect.width) * total;
    let nearest = 0;
    profile.forEach((p, i) => {
      if (Math.abs(p.distance - distance) < Math.abs((profile[nearest]?.distance ?? 0) - distance))
        nearest = i;
    });
    setHover(nearest);
  };

  return (
    <section
      className={`profile${open ? "" : " profile-collapsed"}`}
      aria-label="Perfil de elevação"
    >
      <button
        type="button"
        className="profile-handle"
        aria-expanded={open}
        aria-label={open ? "Recolher perfil de elevação" : "Expandir perfil de elevação"}
        onClick={() => {
          setOpen(!open);
        }}
      >
        {open ? "▾" : "▴"}
      </button>
      {open && (
        <>
          <header className="profile-head">
            <strong>Perfil de elevação</strong>
            <span className="legend-inline">
              <i className="swatch swatch-ground" /> Terreno
              <i className="swatch swatch-drone" /> Drone
              <i className="swatch swatch-zero" /> Decolagem
            </span>
            <span className="muted">
              {(total / 1000).toFixed(2)} km · {low.toFixed(0)} a {high.toFixed(0)} m
            </span>
          </header>
          <div className="profile-chart">
            <svg
              viewBox={`0 0 ${W.toString()} ${H.toString()}`}
              preserveAspectRatio="none"
              role="img"
              aria-label="Terreno e altura do drone ao longo da rota"
              onPointerMove={onMove}
              onPointerLeave={() => {
                setHover(null);
              }}
            >
              <path
                d={`${ground} L${W.toString()},${H.toString()} L0,${H.toString()} Z`}
                className="profile-fill"
              />
              <line
                x1={0}
                x2={W}
                y1={y(0)}
                y2={y(0)}
                className="profile-zero"
                vectorEffect="non-scaling-stroke"
              />
              <path d={ground} className="profile-ground" vectorEffect="non-scaling-stroke" />
              <path
                d={line((p) => p.drone)}
                className="profile-drone"
                vectorEffect="non-scaling-stroke"
              />
              {active && (
                <line
                  x1={x(active.distance)}
                  x2={x(active.distance)}
                  y1={0}
                  y2={H}
                  className="profile-cursor"
                  vectorEffect="non-scaling-stroke"
                />
              )}
            </svg>
            {active && (
              <div
                className="profile-tip"
                role="status"
                style={{ left: `${((active.distance / total) * 100).toFixed(1)}%` }}
              >
                {(active.distance / 1000).toFixed(2)} km · terreno {active.ground.toFixed(0)} m ·
                drone {active.drone.toFixed(0)} m
              </div>
            )}
          </div>
        </>
      )}
    </section>
  );
}
