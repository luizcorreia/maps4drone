import type { Mode, Params } from "../api/types";

export interface Preset {
  mode: Mode;
  title: string;
  description: string;
  /** Applied on top of the current params when the preset is picked. */
  params: Partial<Params>;
}

export const PRESETS: readonly Preset[] = [
  {
    mode: "grid",
    title: "Mapeamento",
    description: "Faixas paralelas para ortofoto e mapa 2D de uma área.",
    params: { altitude: 80, front: 80, side: 70, pitch: -90, angle: null },
  },
  {
    mode: "double_grid",
    title: "Modelo 3D",
    description: "Grade dupla em cruz: mais ângulos de cada ponto, para modelos 3D.",
    params: { altitude: 80, front: 80, side: 70, pitch: -90, angle: null },
  },
  {
    mode: "corridor",
    title: "Corredor",
    description: "Passadas ao longo de uma estrada, rio ou linha de transmissão.",
    params: { altitude: 80, front: 80, side: 70, pitch: -90, lines: 3 },
  },
  {
    mode: "facade",
    title: "Fachada",
    description: "Voo vertical diante de uma parede, com a câmera na horizontal.",
    params: { front: 80, side: 70, speed: 2, wall_height: 20, standoff: 15 },
  },
  {
    mode: "orbit",
    title: "Órbita",
    description: "Círculo em volta de um ponto de interesse, com a câmera apontada para ele.",
    params: { altitude: 40, radius: 40, points: 12, speed: 3, photo_each: true },
  },
  {
    mode: "waypoints",
    title: "Pontos livres",
    description: "Você escolhe cada waypoint, sem grade automática.",
    params: { altitude: 60, speed: 5, pitch: -90, photo_each: false },
  },
];

export function presetFor(mode: Mode): Preset {
  const preset = PRESETS.find((p) => p.mode === mode);
  if (!preset) throw new Error(`no preset for ${mode}`);
  return preset;
}
