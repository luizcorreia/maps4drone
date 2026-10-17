import { useState } from "react";

import type { Mode, Params } from "../api/types";
import { selectDrone, useStore } from "../store";
import { Field, Toggle } from "../ui/Field";

type NumericParam = {
  [K in keyof Params]: Params[K] extends number ? K : never;
}[keyof Params];

const SURVEY_MODES: readonly Mode[] = ["grid", "double_grid", "corridor"];
const TERRAIN_MODES: readonly Mode[] = ["waypoints", ...SURVEY_MODES];

const DEM_LABELS = {
  dsm: "DSM do projeto (inclui árvores e prédios)",
  dtm: "DTM do projeto (só o chão)",
  online: "Online (Open-Meteo, 90 m)",
} as const;

function DemChoice() {
  const task = useStore((s) => s.task);
  const source = useStore((s) => s.demSource);
  const setSource = useStore((s) => s.setDemSource);
  if (!task) return null;
  const available = (key: keyof typeof DEM_LABELS) => key === "online" || task.assets[key];
  return (
    <div className="field">
      <label htmlFor="dem-source">Modelo de elevação</label>
      <select
        id="dem-source"
        value={source}
        onChange={(e) => {
          setSource(e.target.value as keyof typeof DEM_LABELS);
        }}
      >
        {(Object.keys(DEM_LABELS) as (keyof typeof DEM_LABELS)[]).map((key) => (
          <option key={key} value={key} disabled={!available(key)}>
            {DEM_LABELS[key]}
            {available(key) ? "" : " (indisponível)"}
          </option>
        ))}
      </select>
      <p className="field-hint">
        O DSM é o mais seguro para voar: a altura já passa por cima de árvores e construções.
      </p>
    </div>
  );
}

function Terrain() {
  const task = useStore((s) => s.task);
  const terrain = useStore((s) => s.params.terrain);
  const takeoff = useStore((s) => s.params.takeoff);
  const picking = useStore((s) => s.pickingTakeoff);
  const setParam = useStore((s) => s.setParam);
  const setPicking = useStore((s) => s.setPickingTakeoff);
  return (
    <>
      <Toggle
        label="Acompanhar o terreno"
        checked={terrain}
        onChange={(v) => {
          setParam("terrain", v);
        }}
        hint={
          task
            ? "A altura varia para manter a mesma distância do terreno do projeto."
            : "A altura varia para manter a mesma distância do chão. Usa a elevação online (Open-Meteo)."
        }
      />
      {terrain && <DemChoice />}
      {terrain && (
        <div className="field">
          <button
            type="button"
            className={picking ? "primary" : "secondary"}
            onClick={() => {
              setPicking(!picking);
            }}
          >
            {picking
              ? "Clique no mapa…"
              : takeoff
                ? "Mover ponto de decolagem"
                : "Marcar decolagem no mapa"}
          </button>
          {!takeoff && (
            <p className="field-hint warn-text">Necessário para planejar com terreno.</p>
          )}
        </div>
      )}
    </>
  );
}

export function SettingsStep() {
  const mode = useStore((s) => s.mode);
  const params = useStore((s) => s.params);
  const drone = useStore(selectDrone);
  const setParam = useStore((s) => s.setParam);
  const [advanced, setAdvanced] = useState(false);

  const num = (key: NumericParam) => (value: number) => {
    setParam(key, value);
  };
  const maxHeight = drone?.max_height_m ?? 120;
  const survey = SURVEY_MODES.includes(mode);

  return (
    <>
      {mode !== "facade" && (
        <Field
          label={mode === "orbit" ? "Altura do voo" : "Altura sobre o solo"}
          value={params.altitude}
          onChange={num("altitude")}
          min={5}
          max={maxHeight}
          unit="m"
          hint={`Limite do ${drone?.name ?? "drone"}: ${maxHeight.toString()} m.`}
        />
      )}

      {survey && (
        <>
          <Field
            label="Sobreposição frontal"
            value={params.front}
            onChange={num("front")}
            min={50}
            max={95}
            unit="%"
          />
          <Field
            label="Sobreposição lateral"
            value={params.side}
            onChange={num("side")}
            min={40}
            max={90}
            unit="%"
          />
        </>
      )}

      {mode === "corridor" && (
        <Field
          label="Passadas"
          value={params.lines}
          onChange={num("lines")}
          min={1}
          max={15}
          hint="Número ímpar: uma sobre o eixo e uma de cada lado por par."
        />
      )}

      {(mode === "grid" || mode === "double_grid") && (
        <>
          <Toggle
            label="Ângulo automático"
            checked={params.angle === null}
            onChange={(auto) => {
              setParam("angle", auto ? null : 0);
            }}
            hint="As faixas seguem o eixo maior da área, o que reduz curvas e bateria."
          />
          {params.angle !== null && (
            <Field
              label="Ângulo das faixas"
              value={params.angle}
              onChange={(v) => {
                setParam("angle", v);
              }}
              min={0}
              max={179}
              unit="°"
              hint="0° = norte, 90° = leste."
            />
          )}
        </>
      )}

      {mode === "facade" && (
        <>
          <Field
            label="Altura da parede"
            value={params.wall_height}
            onChange={num("wall_height")}
            min={2}
            max={maxHeight}
            unit="m"
          />
          <Field
            label="Distância da parede"
            value={params.standoff}
            onChange={num("standoff")}
            min={3}
            max={60}
            unit="m"
          />
          <div className="field">
            <label htmlFor="wall-side">Lado da parede</label>
            <select
              id="wall-side"
              value={params.wall_side}
              onChange={(e) => {
                setParam("wall_side", e.target.value === "right" ? "right" : "left");
              }}
            >
              <option value="left">Esquerda do trajeto A→B</option>
              <option value="right">Direita do trajeto A→B</option>
            </select>
          </div>
          <Field
            label="Sobreposição frontal"
            value={params.front}
            onChange={num("front")}
            min={50}
            max={95}
            unit="%"
          />
          <Field
            label="Sobreposição lateral"
            value={params.side}
            onChange={num("side")}
            min={40}
            max={90}
            unit="%"
          />
        </>
      )}

      {mode === "orbit" && (
        <>
          <Field
            label="Raio"
            value={params.radius}
            onChange={num("radius")}
            min={5}
            max={500}
            unit="m"
          />
          <Field
            label="Pontos na órbita"
            value={params.points}
            onChange={num("points")}
            min={3}
            max={72}
          />
          <Field
            label="Altura do alvo"
            value={params.target_height}
            onChange={num("target_height")}
            min={0}
            max={100}
            unit="m"
            hint="A câmera aponta para esta altura no ponto central."
          />
          <Toggle
            label="Foto em cada ponto"
            checked={params.photo_each}
            onChange={(v) => {
              setParam("photo_each", v);
            }}
          />
        </>
      )}

      {(mode === "waypoints" || mode === "orbit" || mode === "facade") && (
        <Field
          label="Velocidade"
          value={params.speed}
          onChange={num("speed")}
          min={1}
          max={drone?.max_speed_ms ?? 15}
          step={0.5}
          unit="m/s"
        />
      )}

      {survey && drone && (
        <div className="field">
          <label htmlFor="interval">Intervalo de disparo</label>
          <select
            id="interval"
            value={params.interval}
            onChange={(e) => {
              setParam("interval", Number(e.target.value));
            }}
          >
            {drone.shoot_intervals_s.map((s) => (
              <option key={s} value={s}>{`${s.toString()} s`}</option>
            ))}
          </select>
          <p className="field-hint">
            {drone.export_format === "atom2"
              ? "Configure o mesmo intervalo no temporizador da câmera do app."
              : "Define a velocidade de voo; as fotos saem em cada waypoint."}
          </p>
        </div>
      )}

      {TERRAIN_MODES.includes(mode) && <Terrain />}

      <button
        type="button"
        className="link"
        aria-expanded={advanced}
        onClick={() => {
          setAdvanced(!advanced);
        }}
      >
        {advanced ? "Ocultar avançado" : "Mostrar avançado"}
      </button>

      {advanced && (
        <div className="advanced">
          {drone && Object.keys(drone.cameras).length > 1 && (
            <div className="field">
              <label htmlFor="camera">Câmera</label>
              <select
                id="camera"
                value={params.camera ?? drone.default_camera}
                onChange={(e) => {
                  setParam("camera", e.target.value);
                }}
              >
                {Object.keys(drone.cameras).map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </div>
          )}
          {mode !== "facade" && mode !== "orbit" && (
            <Field
              label="Inclinação do gimbal"
              value={params.pitch}
              onChange={num("pitch")}
              min={-90}
              max={20}
              unit="°"
              hint="-90° aponta para baixo."
            />
          )}
          {(mode === "grid" || mode === "double_grid") && (
            <Field
              label="Aumentar a área em"
              value={params.margin}
              onChange={num("margin")}
              min={0}
              max={200}
              unit="m"
            />
          )}
          {params.terrain && (
            <Field
              label="Espaçamento das amostras de terreno"
              value={params.terrain_step}
              onChange={num("terrain_step")}
              min={5}
              max={200}
              unit="m"
            />
          )}
        </div>
      )}
    </>
  );
}
