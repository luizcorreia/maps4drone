import { useState } from "react";

import { searchPlaces, type Place } from "../api/geocode";
import { useStore } from "../store";

const LOCATE_SPAN_DEG = 0.0015;

type Outcome =
  { kind: "idle" } | { kind: "found"; places: Place[] } | { kind: "error"; text: string };

/** Finds a place by name or by the device's position, and sends the map there. */
export function PlaceSearch() {
  const showBounds = useStore((s) => s.showBounds);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<Outcome>({ kind: "idle" });

  const search = async () => {
    const text = query.trim();
    if (!text || busy) return;
    setBusy(true);
    try {
      const places = await searchPlaces(text);
      if (places.length === 1 && places[0]) showBounds(places[0].bounds);
      setOutcome({ kind: "found", places });
    } catch (err) {
      setOutcome({ kind: "error", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setBusy(false);
    }
  };

  const locate = () => {
    if (!("geolocation" in navigator)) {
      setOutcome({ kind: "error", text: "Este navegador não informa a posição." });
      return;
    }
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        const { latitude: lat, longitude: lng } = coords;
        showBounds([
          [lat - LOCATE_SPAN_DEG, lng - LOCATE_SPAN_DEG],
          [lat + LOCATE_SPAN_DEG, lng + LOCATE_SPAN_DEG],
        ]);
        setOutcome({ kind: "idle" });
      },
      () => {
        setOutcome({ kind: "error", text: "Não foi possível obter a sua posição." });
      },
      { timeout: 8000 },
    );
  };

  return (
    <div className="place-search">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void search();
        }}
        role="search"
      >
        <input
          type="search"
          aria-label="Buscar lugar"
          placeholder="Buscar endereço ou lugar"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
          }}
        />
        <button type="submit" className="primary" disabled={busy || query.trim() === ""}>
          {busy ? "…" : "Buscar"}
        </button>
        <button
          type="button"
          className="secondary"
          title="Ir para a minha posição"
          onClick={locate}
        >
          Minha posição
        </button>
      </form>

      {outcome.kind === "found" && (
        <ul className="place-results" aria-label="Resultados da busca">
          {outcome.places.length === 0 && (
            <li className="muted">Nenhum resultado. Tente só a cidade ou o nome do lugar.</li>
          )}
          {outcome.places.length > 1 &&
            outcome.places.map((place) => (
              <li key={place.label}>
                <button
                  type="button"
                  onClick={() => {
                    showBounds(place.bounds);
                    setOutcome({ kind: "idle" });
                  }}
                >
                  {place.label}
                </button>
              </li>
            ))}
        </ul>
      )}
      {outcome.kind === "error" && (
        <p role="alert" className="error-text">
          {outcome.text}
        </p>
      )}
    </div>
  );
}
