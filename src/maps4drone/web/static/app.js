"use strict";

const MODES = [
  { id: "waypoints", label: "Waypoints", store: "waypoints", min: 1,
    hint: "Clique no mapa para adicionar waypoints." },
  { id: "grid", label: "Grid", store: "area", min: 3,
    hint: "Clique para marcar os vértices da área (mínimo 3)." },
  { id: "double_grid", label: "Double Grid", store: "area", min: 3,
    hint: "Duas passadas perpendiculares sobre a área: bom para modelos 3D." },
  { id: "corridor", label: "Corredor", store: "line", min: 2,
    hint: "Clique para desenhar o eixo da estrada, ferrovia ou rio." },
  { id: "facade", label: "Fachada", store: "facade", min: 2, max: 2,
    hint: "Marque as duas pontas da base da parede (A e B). Decole na altura do chão." },
  { id: "orbit", label: "Órbita", store: "orbit", min: 1, max: 1,
    hint: "Clique no ponto de interesse para orbitar." },
];
const MODE_DEFAULTS = {
  waypoints: { speed: 5 }, orbit: { speed: 3 }, facade: { speed: 1.5, front: 75, side: 70 },
  grid: { front: 80, side: 70 }, double_grid: { front: 80, side: 70 }, corridor: { front: 80, side: 70 },
};

const state = {
  mode: "grid",
  points: { area: [], line: [], facade: [], orbit: [], waypoints: [] }, // [lat, lng]
  takeoff: null, pickingTakeoff: false, drones: [], seq: 0, timer: null, ok: false,
};

const $ = (id) => document.getElementById(id);
const paramEls = () => [...document.querySelectorAll("[data-param]")];
const mode = () => MODES.find((m) => m.id === state.mode);
const pts = () => state.points[mode().store];

const map = L.map("map", { zoomControl: true }).setView([-23.42, -51.93], 14);
const street = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19, attribution: "&copy; OpenStreetMap",
});
const satellite = L.tileLayer(
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  { maxZoom: 19, attribution: "Tiles &copy; Esri" },
);
street.addTo(map);
const shapeLayer = L.layerGroup().addTo(map);
const routeLayer = L.layerGroup().addTo(map);
let takeoffMarker = null;

// ---- parameters ------------------------------------------------------------

function collectParams() {
  const params = { drone: $("drone").value };
  for (const el of paramEls()) {
    const key = el.dataset.param;
    if (el.type === "checkbox") params[key] = el.checked;
    else if (el.type === "range" || "num" in el.dataset) params[key] = Number(el.value);
    else if (el.value) params[key] = el.value;
  }
  if (state.takeoff) params.takeoff = [state.takeoff[1], state.takeoff[0]];
  return params;
}

function geometry() {
  const m = mode();
  const p = pts();
  if (p.length < m.min) return null;
  const lonlat = p.map(([lat, lng]) => [lng, lat]);
  if (m.store === "area") return { type: "Polygon", coordinates: [[...lonlat, lonlat[0]]] };
  if (m.store === "orbit") return { type: "Point", coordinates: lonlat[0] };
  if (m.store === "waypoints") return { type: "MultiPoint", coordinates: lonlat };
  return { type: "LineString", coordinates: lonlat };
}

function body() {
  return { mode: state.mode, geometry: geometry(), params: collectParams() };
}

// ---- rendering -------------------------------------------------------------

function vertexIcon(label, cls) {
  return L.divIcon({ className: cls, html: String(label), iconSize: [20, 20] });
}

function drawShape() {
  shapeLayer.clearLayers();
  const m = mode();
  const p = pts();
  if (p.length > 1 && m.store !== "waypoints") {
    const opts = { color: "#2b5fd9", weight: 2, fillOpacity: 0.12 };
    (m.store === "area" && p.length > 2 ? L.polygon(p, opts) : L.polyline(p, opts)).addTo(shapeLayer);
  }
  p.forEach((latlng, i) => {
    const marker = L.marker(latlng, { icon: vertexIcon(i + 1, "vertex"), draggable: true });
    marker.on("dragend", () => { p[i] = [marker.getLatLng().lat, marker.getLatLng().lng]; changed(); });
    marker.on("contextmenu", () => { p.splice(i, 1); changed(); });
    marker.addTo(shapeLayer);
  });
}

function drawTakeoff() {
  if (takeoffMarker) takeoffMarker.remove();
  takeoffMarker = null;
  if (state.takeoff) {
    takeoffMarker = L.marker(state.takeoff, { icon: vertexIcon("H", "takeoff"), draggable: true })
      .addTo(map);
    takeoffMarker.on("dragend", () => {
      const { lat, lng } = takeoffMarker.getLatLng();
      state.takeoff = [lat, lng];
      changed();
    });
  }
  $("takeoff-info").textContent = state.takeoff
    ? `Decolagem: ${state.takeoff[0].toFixed(6)}, ${state.takeoff[1].toFixed(6)}`
    : "Sem ponto de decolagem definido.";
}

function drawRoute(geojson) {
  routeLayer.clearLayers();
  if (!geojson) return;
  const feats = geojson.features;
  const route = feats.find((f) => f.properties.kind === "route");
  const latlngs = route.geometry.coordinates.map(([lng, lat]) => [lat, lng]);
  L.polyline(latlngs, { color: "#e07b00", weight: 3 }).addTo(routeLayer);
  if (feats.length <= 500) {
    for (const ll of latlngs) {
      L.circleMarker(ll, { radius: 3, color: "#e07b00", fillOpacity: 1 }).addTo(routeLayer);
    }
  }
}

const fmtTime = (s) => `~${Math.floor(s / 60)}min ${String(Math.round(s % 60)).padStart(2, "0")}s`;

function showStats(res) {
  const s = res && res.stats;
  $("st-wp").textContent = s ? s.waypoints : "—";
  $("st-dist").textContent = s ? `${(s.distance_m / 1000).toFixed(2)} km` : "—";
  $("st-time").textContent = s ? fmtTime(s.duration_s) : "—";
  $("st-bat").textContent = s ? s.batteries : "—";
  $("st-img").textContent = s
    ? Object.entries(s.images).map(([i, n]) => `${i}s: ~${n}`).join(" · ") : "—";
  $("st-area").textContent = s && s.area_ha != null ? `${s.area_ha.toFixed(2)} ha` : "—";
  const altEl = document.querySelector('[data-param="altitude"]');
  $("st-alt").textContent = ["facade"].includes(state.mode) ? "—" : `${altEl.value} m`;
  $("st-speed").textContent = res ? `${res.speed.toFixed(1)} m/s` : "—";
}

function showNotices(res, error) {
  const timer = $("timer");
  timer.hidden = !(res && res.interval);
  if (res && res.interval) {
    timer.textContent =
      `Ative o modo temporizado de fotos no app com intervalo de ${res.interval} s antes de voar: ` +
      "o arquivo da missão não dispara a câmera.";
  }
  const list = $("warnings");
  list.replaceChildren(...((res && res.warnings) || []).map((w) => {
    const li = document.createElement("li");
    li.textContent = w;
    return li;
  }));
  list.hidden = !list.children.length;
  $("error").hidden = !error;
  $("error").textContent = error || "";
}

// ---- server calls ----------------------------------------------------------

function errorText(data) {
  if (!data || !data.detail) return "erro desconhecido";
  if (typeof data.detail === "string") return data.detail;
  return data.detail.map((d) => `${d.loc.slice(-1)[0]}: ${d.msg}`).join("; ");
}

async function replan() {
  const seq = ++state.seq;
  updateCameraInfo();
  if (!geometry()) {
    state.ok = false;
    drawRoute(null); showStats(null); showNotices(null, null);
    $("export").disabled = true;
    return;
  }
  let res = null, error = null;
  try {
    const r = await fetch("/api/plan", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body()),
    });
    const data = await r.json();
    if (r.ok) res = data; else error = errorText(data);
  } catch (e) {
    error = "não foi possível falar com o servidor";
  }
  if (seq !== state.seq) return; // a newer request superseded this one
  state.ok = Boolean(res);
  $("export").disabled = !res;
  drawRoute(res && res.geojson);
  showStats(res);
  showNotices(res, error);
}

async function updateCameraInfo() {
  const p = collectParams();
  const q = new URLSearchParams({ drone: p.drone, altitude: p.altitude });
  if (p.camera) q.set("camera", p.camera);
  try {
    const r = await fetch(`/api/camera?${q}`);
    if (!r.ok) return;
    const c = await r.json();
    $("caminfo").textContent =
      `GSD ${c.gsd_cm.toFixed(2)} cm/px · cobertura ${c.footprint_w_m.toFixed(1)} × ` +
      `${c.footprint_h_m.toFixed(1)} m`;
  } catch (e) { /* the info line is optional */ }
}

async function exportMission() {
  const r = await fetch("/api/export", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body()),
  });
  if (!r.ok) { showNotices(null, errorText(await r.json())); return; }
  const blob = await r.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = /filename="(.+)"/.exec(r.headers.get("Content-Disposition") || "")?.[1] || "missao.zip";
  a.click();
  URL.revokeObjectURL(a.href);
}

async function importFile(file) {
  const r = await fetch(`/api/import?name=${encodeURIComponent(file.name)}`, {
    method: "POST", body: file,
  });
  const data = await r.json();
  if (!r.ok) { showNotices(null, errorText(data)); return; }
  const flip = (coords) => coords.map(([lng, lat]) => [lat, lng]);
  if (data.polygon) {
    const ring = data.polygon.type === "Polygon"
      ? data.polygon.coordinates[0] : data.polygon.coordinates[0][0];
    state.points.area = flip(ring.slice(0, -1));
  }
  if (data.line) state.points.line = flip(data.line.coordinates);
  if (!["grid", "double_grid", "corridor"].includes(state.mode)) {
    setMode(data.polygon ? "grid" : "corridor");
  }
  const all = pts();
  if (all.length) map.fitBounds(all);
  changed();
}

// ---- interaction -----------------------------------------------------------

function changed() {
  drawShape();
  clearTimeout(state.timer);
  state.timer = setTimeout(replan, 300);
}

function addPoint(latlng) {
  const m = mode();
  const p = pts();
  const point = [latlng.lat, latlng.lng];
  if (m.max && p.length >= m.max) p[p.length - 1] = point;
  else p.push(point);
  changed();
}

map.on("click", (e) => {
  if (state.pickingTakeoff) {
    state.takeoff = [e.latlng.lat, e.latlng.lng];
    setPicking(false);
    drawTakeoff();
    changed();
  } else {
    addPoint(e.latlng);
  }
});

function setPicking(on) {
  state.pickingTakeoff = on;
  $("pick-takeoff").classList.toggle("on", on);
  map.getContainer().style.cursor = on ? "crosshair" : "";
}

function applyModeVisibility() {
  for (const el of document.querySelectorAll("[data-modes]")) {
    el.hidden = !el.dataset.modes.split(" ").includes(state.mode);
  }
  $("alt-label").textContent = state.mode === "orbit" ? "Altura do voo (m)" : "Altitude (m)";
  $("hint").textContent = mode().hint;
  document.querySelectorAll("#tabs button").forEach((b) => {
    b.setAttribute("aria-selected", String(b.dataset.mode === state.mode));
  });
}

function setParam(key, value) {
  const el = document.querySelector(`[data-param="${key}"]`);
  el.value = value;
  syncOutput(el);
}

function setMode(id) {
  state.mode = id;
  for (const [k, v] of Object.entries(MODE_DEFAULTS[id] || {})) setParam(k, v);
  applyModeVisibility();
  changed();
}

function syncOutput(el) {
  const out = el.closest("label")?.querySelector("output");
  if (out) out.textContent = el.value;
}

// ---- setup -----------------------------------------------------------------

function fillSelect(select, values, selected) {
  select.replaceChildren(...values.map((v) => {
    const o = document.createElement("option");
    o.value = o.textContent = String(v);
    o.selected = v === selected;
    return o;
  }));
}

function useDrone(drone) {
  fillSelect($("camera"), Object.keys(drone.cameras), drone.default_camera);
  fillSelect($("interval"), drone.shoot_intervals_s, 3);
  const speed = document.querySelector('[data-param="speed"]');
  speed.max = drone.max_speed_ms;
}

async function init() {
  const tabs = $("tabs");
  for (const m of MODES) {
    const b = document.createElement("button");
    b.type = "button"; b.role = "tab"; b.textContent = m.label; b.dataset.mode = m.id;
    b.addEventListener("click", () => setMode(m.id));
    tabs.append(b);
  }
  for (const el of paramEls()) {
    syncOutput(el);
    el.addEventListener("input", () => { syncOutput(el); changed(); });
  }
  $("terrain").addEventListener("change", () => {
    $("terrain-opts").hidden = !$("terrain").checked;
    if (!$("terrain").checked) setPicking(false);
  });
  $("sat").addEventListener("click", () => {
    const useSat = !map.hasLayer(satellite);
    (useSat ? satellite : street).addTo(map);
    (useSat ? street : satellite).remove();
    $("sat").textContent = useSat ? "Mapa" : "Satélite";
  });
  $("pick-takeoff").addEventListener("click", () => setPicking(!state.pickingTakeoff));
  $("clear-takeoff").addEventListener("click", () => { state.takeoff = null; drawTakeoff(); changed(); });
  $("undo").addEventListener("click", () => { pts().pop(); changed(); });
  $("clear").addEventListener("click", () => { pts().length = 0; changed(); });
  $("export").addEventListener("click", exportMission);
  $("import").addEventListener("change", (e) => {
    if (e.target.files[0]) importFile(e.target.files[0]);
    e.target.value = "";
  });
  $("search").addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = $("q").value.trim();
    if (!q) return;
    try {
      const r = await fetch(
        `https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${encodeURIComponent(q)}`);
      const [hit] = await r.json();
      if (hit) map.setView([Number(hit.lat), Number(hit.lon)], 15);
      else $("hint").textContent = "Local não encontrado.";
    } catch (err) {
      $("hint").textContent = "Falha na busca.";
    }
  });
  $("drone").addEventListener("change", () => {
    useDrone(state.drones.find((d) => d.id === $("drone").value));
    changed();
  });

  state.drones = await (await fetch("/api/drones")).json();
  fillSelect($("drone"), state.drones.map((d) => d.id), state.drones[0].id);
  for (const opt of $("drone").options) opt.textContent = state.drones.find((d) => d.id === opt.value).name;
  useDrone(state.drones[0]);
  drawTakeoff();
  setMode("grid");
}

init();
