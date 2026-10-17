import { useStore } from "../store";

export function Legend() {
  const hasPlan = useStore((s) => s.plan !== null);
  const takeoff = useStore((s) => s.params.takeoff !== null);
  const shots = useStore((s) => s.showShots && s.shots !== null);
  if (!hasPlan) return null;
  return (
    <ul className="legend" aria-label="Legenda">
      <li>
        <i className="swatch swatch-area" /> Área desenhada
      </li>
      <li>
        <i className="swatch swatch-route" /> Rota
      </li>
      <li>
        <i className="swatch swatch-wp" /> Waypoint
      </li>
      <li>
        <i className="swatch swatch-start">I</i> Início
      </li>
      <li>
        <i className="swatch swatch-end">F</i> Fim
      </li>
      {shots && (
        <li>
          <i className="swatch swatch-shot" /> Foto tirada
        </li>
      )}
      {takeoff && (
        <li>
          <i className="swatch swatch-takeoff">D</i> Decolagem
        </li>
      )}
    </ul>
  );
}
