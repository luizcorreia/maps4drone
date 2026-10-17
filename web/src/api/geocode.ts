/** A place found by name: its label and the box the map should frame. */
export interface Place {
  label: string;
  /** [[south, west], [north, east]] */
  bounds: [[number, number], [number, number]];
}

interface NominatimHit {
  display_name?: string;
  lat?: string;
  lon?: string;
  /** [south, north, west, east], as strings. */
  boundingbox?: string[];
}

const MIN_SPAN_DEG = 0.002; // a point-like hit (a house) still deserves a neighbourhood

const isNumber = (v: number | undefined): v is number => v !== undefined && Number.isFinite(v);

/** Turns Nominatim's hit into a box, widening the tiny ones; null when it has no position. */
export function toPlace(hit: NominatimHit): Place | null {
  const box = hit.boundingbox?.map(Number);
  const lat = Number(hit.lat);
  const lon = Number(hit.lon);
  if (!hit.display_name) return null;
  const [south, north, west, east] = box?.length === 4 ? box : [lat, lat, lon, lon];
  if (!isNumber(south) || !isNumber(north) || !isNumber(west) || !isNumber(east)) return null;
  const padLat = Math.max(0, (MIN_SPAN_DEG - (north - south)) / 2);
  const padLng = Math.max(0, (MIN_SPAN_DEG - (east - west)) / 2);
  return {
    label: hit.display_name,
    bounds: [
      [south - padLat, west - padLng],
      [north + padLat, east + padLng],
    ],
  };
}

const RETRY_AFTER_MS = 1100; // Nominatim allows one request per second

async function lookup(query: string, signal?: AbortSignal): Promise<Place[]> {
  const url = new URL("https://nominatim.openstreetmap.org/search");
  url.searchParams.set("q", query);
  url.searchParams.set("format", "jsonv2");
  url.searchParams.set("limit", "5");
  url.searchParams.set("accept-language", "pt-BR");
  const res = await fetch(url, { signal });
  if (!res.ok) throw new Error(`A busca de lugares falhou (${res.status.toString()}).`);
  const hits = (await res.json()) as NominatimHit[];
  return hits.flatMap((hit) => toPlace(hit) ?? []);
}

/**
 * Looks a place up on OpenStreetMap's Nominatim. Call it only when the user asks (no
 * search-as-you-type): the service's usage policy allows one request per second and no
 * autocomplete. A comma-separated address that finds nothing is tried once more as plain words,
 * which Nominatim often matches when it rejects the commas ("Rua X, Cidade, Estado").
 */
export async function searchPlaces(query: string, signal?: AbortSignal): Promise<Place[]> {
  const places = await lookup(query, signal);
  if (places.length > 0 || !query.includes(",")) return places;
  await new Promise((resolve) => setTimeout(resolve, RETRY_AFTER_MS));
  return lookup(query.replace(/,/g, " ").replace(/\s+/g, " ").trim(), signal);
}
