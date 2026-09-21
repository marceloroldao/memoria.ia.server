const NS = "http://www.w3.org/2000/svg";
const $ = (selector) => document.querySelector(selector);
let snapshotCache = null;
const WORLD = { width: 1100, height: 720 };
const camera = { x: 0, y: 0, width: WORLD.width, height: WORLD.height, minWidth: 95, maxWidth: WORLD.width };
const temporal = { offset: 0, limit: 900, total: 0, minLimit: 64, maxLimit: 1200 };
let dragging = null;
let loadTimer = null;
let selectedEpisodeId = null;

function svg(name, attrs = {}) {
  const el = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
}
function metric(label, value) {
  const el = document.createElement("div");
  el.className = "metric";
  el.innerHTML = `<span class="label">${label}</span><span class="value">${value}</span>`;
  return el;
}
function renderMetrics(stats) {
  const root = $("#metrics");
  root.replaceChildren();
  const values = [
    ["registros", stats.records ?? 0],
    ["visíveis", stats.visible_records ?? 0],
    ["buckets janela", stats.occupied_buckets ?? 0],
    ["carga janela", Number(stats.load_factor ?? 0).toFixed(5)],
    ["fases janela", stats.phase_slots ?? 0],
  ];
  for (const item of values) root.appendChild(metric(...item));
}
function renderCapabilities(observation) {
  const root = $("#capabilities");
  root.replaceChildren();
  for (const [name, c] of Object.entries(observation.capabilities ?? {})) {
    const row = document.createElement("div");
    row.className = `capability ${c.available ? "available" : "unavailable"}`;
    row.innerHTML = `<span>${name.replaceAll("_", " ")}</span><small>${c.available ? "disponível" : "aguarda contrato público"}</small>`;
    if (c.reason) row.title = c.reason;
    root.appendChild(row);
  }
}

function safe(value) {
  return value === null || value === undefined || value === "" ? "—" : String(value);
}
function showNode(node, group) {
  document.querySelectorAll(".node.active").forEach((i) => i.classList.remove("active"));
  group.classList.add("active");
  selectedEpisodeId = String(node.episode?.episode_id ?? "");
  $("#inspector-empty").hidden = true;
  const panel = $("#inspector");
  panel.hidden = false;
  const episode = node.episode ?? {};
  const fields = [
    ["BDR record ID", node.id],
    ["índice temporal", node.temporal_index],
    ["episode_id", episode.episode_id],
    ["session_id", episode.session_id],
    ["ordem", episode.order],
    ["timestamp", episode.timestamp],
    ["event_type", episode.event_type],
    ["role", episode.role],
    ["topics", episode.topics_csv],
    ["source_type", episode.source_type],
    ["source_authority", episode.source_authority],
    ["ultimate_source", episode.ultimate_source_memory_id],
    ["ρR / região", node.rho_R],
    ["φ / fase", node.phi],
    ["θ / direção", Number(node.theta).toFixed(8)],
    ["fν", Number(node.f_nu).toFixed(8)],
    ["payload bytes", node.payload_size],
    ["fingerprint", node.fingerprint],
    ["payload preview", node.payload_preview, "payload"],
  ];
  panel.replaceChildren();
  for (const [label, value, className] of fields) {
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    if (className) dd.className = className;
    dd.textContent = safe(value);
    panel.append(dt, dd);
  }
}

function nodePosition(node, stats) {
  const cx = 550, cy = 345, maxRadius = 285;
  const bucketCount = Math.max(Number(stats.bucket_count ?? 1), 1);
  const normalizedRho = Math.min(Math.max(Number(node.rho_R) / Math.max(bucketCount - 1, 1), 0), 1);
  const radius = 28 + normalizedRho * (maxRadius - 28);
  const angle = Number(node.theta) - Math.PI / 2;
  return { x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius };
}
function zoomLevel() { return WORLD.width / camera.width; }
function visible(p, margin = 18) {
  return p.x >= camera.x - margin && p.x <= camera.x + camera.width + margin &&
         p.y >= camera.y - margin && p.y <= camera.y + camera.height + margin;
}
function clampCamera() {
  camera.width = Math.min(Math.max(camera.width, camera.minWidth), camera.maxWidth);
  camera.height = camera.width * (WORLD.height / WORLD.width);
  camera.x = Math.min(Math.max(camera.x, 0), WORLD.width - camera.width);
  camera.y = Math.min(Math.max(camera.y, 0), WORLD.height - camera.height);
}
function updateCamera() {
  const map = $("#map");
  map.setAttribute("viewBox", `${camera.x} ${camera.y} ${camera.width} ${camera.height}`);
  const z = zoomLevel();
  $("#zoom-state").textContent = `zoom ${z.toFixed(1)}× · temporal`;
}
function temporalBounds(limit = temporal.limit) {
  const total = Math.max(0, temporal.total);
  const maxAllowed = total > 0 ? Math.min(temporal.maxLimit, total) : temporal.maxLimit;
  const minAllowed = total > 0 ? Math.min(temporal.minLimit, total) : 1;
  return {
    min: Math.max(1, minAllowed),
    max: Math.max(1, maxAllowed),
  };
}
function clampTemporal(offset, limit) {
  const bounds = temporalBounds(limit);
  const nextLimit = Math.max(bounds.min, Math.min(bounds.max, Math.round(limit)));
  const maxOffset = Math.max(0, temporal.total - nextLimit);
  return {
    limit: nextLimit,
    offset: Math.max(0, Math.min(maxOffset, Math.round(offset))),
  };
}
async function fetchSnapshot(offset, limit) {
  const response = await fetch(`/api/bdr-explorer/v1/snapshot?offset=${offset}&limit=${limit}`, { cache: "no-store" });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || body.error || `snapshot HTTP ${response.status}`);
  return body;
}
async function loadWindow(offset = temporal.offset, limit = temporal.limit) {
  const clamped = clampTemporal(offset, limit);
  const snapshot = await fetchSnapshot(clamped.offset, clamped.limit);
  snapshotCache = snapshot;
  const windowInfo = snapshot.window ?? {};
  temporal.total = Number(windowInfo.total ?? snapshot.statistics?.records ?? 0);
  temporal.offset = Number(windowInfo.offset ?? clamped.offset);
  temporal.limit = Math.max(1, Number(windowInfo.limit ?? clamped.limit));
  renderMetrics(snapshot.statistics ?? {});
  renderCurrent();
}
function scheduleWindowLoad(offset, limit) {
  const clamped = clampTemporal(offset, limit);
  temporal.offset = clamped.offset;
  temporal.limit = clamped.limit;
  clearTimeout(loadTimer);
  loadTimer = setTimeout(() => {
    loadWindow(temporal.offset, temporal.limit).catch((error) => {
      $("#viewport-state").textContent = `falha temporal: ${error.message}`;
      console.error(error);
    });
  }, 120);
}
function zoomAt(factor, clientX, clientY) {
  const map = $("#map"), rect = map.getBoundingClientRect();
  const rx = Math.min(1, Math.max(0, (clientX - rect.left) / Math.max(rect.width, 1)));
  const ry = Math.min(1, Math.max(0, (clientY - rect.top) / Math.max(rect.height, 1)));
  const wx = camera.x + rx * camera.width;
  const wy = camera.y + ry * camera.height;
  camera.width *= factor;
  clampCamera();
  camera.x = wx - rx * camera.width;
  camera.y = wy - ry * camera.height;
  clampCamera();

  const anchor = temporal.offset + rx * temporal.limit;
  const wantedLimit = temporal.limit * factor;
  const next = clampTemporal(anchor - rx * wantedLimit, wantedLimit);
  temporal.offset = next.offset;
  temporal.limit = next.limit;

  // Re-render immediately: nodes outside the spatial viewport leave the DOM now.
  renderCurrent();
  scheduleWindowLoad(next.offset, next.limit);
}
function resetCamera() {
  Object.assign(camera, { x: 0, y: 0, width: WORLD.width, height: WORLD.height });
  const limit = Math.min(temporal.maxLimit, Math.max(1, temporal.total || temporal.maxLimit));
  const offset = Math.max(0, temporal.total - limit);
  updateCamera();
  scheduleWindowLoad(offset, limit);
}
function shiftTime(direction) {
  const step = Math.max(1, Math.round(temporal.limit * 0.8));
  scheduleWindowLoad(temporal.offset + direction * step, temporal.limit);
}

function renderMap(nodes, stats) {
  const map = $("#map");
  map.replaceChildren();
  const cx = 550, cy = 345;
  for (const r of [72, 142, 214, 285]) map.appendChild(svg("circle", { cx, cy, r, class: "orbit" }));
  map.appendChild(svg("line", { x1: 120, y1: cy, x2: 980, y2: cy, class: "axis" }));
  map.appendChild(svg("line", { x1: cx, y1: 40, x2: cx, y2: 650, class: "axis" }));
  map.appendChild(svg("circle", { cx, cy, r: 4, fill: "rgba(159,240,207,.92)" }));

  const z = zoomLevel();
  const positioned = nodes.map((n) => ({ node: n, p: nodePosition(n, stats) })).filter((v) => visible(v.p));
  const cap = z < 1.7 ? 180 : z < 3 ? 450 : z < 5 ? 900 : 1200;
  const stride = Math.max(1, Math.ceil(positioned.length / cap));
  const draw = positioned.filter((_, i) => i % stride === 0);

  for (const { node, p } of draw) {
    const size = 5 + Math.min(Math.max(Number(node.f_nu), 0), 1) * 8;
    const group = svg("g", { class: "node", tabindex: "0", "aria-label": `Estado BDR ${node.id}` });
    group.appendChild(svg("circle", { cx: p.x.toFixed(2), cy: p.y.toFixed(2), r: size.toFixed(2) }));
    if (z >= 2.2 && draw.length <= 500) {
      const label = svg("text", { x: (p.x + size + 5).toFixed(2), y: (p.y + 3).toFixed(2), class: "node-label" });
      label.textContent = `#${node.id}`;
      group.appendChild(label);
    }
    group.addEventListener("pointerdown", (event) => event.stopPropagation());
    group.addEventListener("click", (event) => { event.stopPropagation(); showNode(node, group); });
    group.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); showNode(node, group); }
    });
    if (selectedEpisodeId && String(node.episode?.episode_id ?? "") === selectedEpisodeId) group.classList.add("active");
    map.appendChild(group);
  }

  const first = temporal.total ? temporal.offset + 1 : 0;
  const last = Math.min(temporal.total, temporal.offset + Number(snapshotCache?.window?.returned ?? nodes.length));
  $("#viewport-state").textContent =
    `${draw.length} renderizados · ${nodes.length} carregados · tempo ${first}–${last}/${temporal.total}${stride > 1 ? ` · LOD 1/${stride}` : ""}`;
  updateCamera();
}
function matches(node, query) {
  if (!query) return true;
  const episode = node.episode ?? {};
  return [
    node.id, node.rho_R, node.phi, node.fingerprint, node.payload_preview,
    episode.episode_id, episode.session_id, episode.event_type, episode.topics_csv,
    episode.source_type, episode.ultimate_source_memory_id, episode.timestamp,
  ].map((v) => String(v ?? "").toLowerCase()).join(" ").includes(query.toLowerCase());
}
function renderCurrent() {
  if (!snapshotCache) return;
  const q = $("#search").value.trim();
  renderMap((snapshotCache.nodes ?? []).filter((n) => matches(n, q)), snapshotCache.statistics ?? {});
}
function bindNavigation() {
  const map = $("#map");
  map.addEventListener("wheel", (event) => {
    event.preventDefault();
    zoomAt(event.deltaY < 0 ? 0.82 : 1.22, event.clientX, event.clientY);
  }, { passive: false });

  map.addEventListener("pointerdown", (event) => {
    if (event.target.closest?.(".node")) return;
    dragging = { x: event.clientX, y: event.clientY, cx: camera.x, cy: camera.y, moved: false };
    map.setPointerCapture(event.pointerId);
    map.classList.add("dragging");
  });
  map.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    if (Math.abs(event.clientX - dragging.x) > 2 || Math.abs(event.clientY - dragging.y) > 2) dragging.moved = true;
    const rect = map.getBoundingClientRect();
    camera.x = dragging.cx - (event.clientX - dragging.x) * camera.width / Math.max(rect.width, 1);
    camera.y = dragging.cy - (event.clientY - dragging.y) * camera.height / Math.max(rect.height, 1);
    clampCamera();
    if (dragging.moved) renderCurrent();
    else updateCamera();
  });
  const end = () => {
    if (!dragging) return;
    dragging = null;
    map.classList.remove("dragging");
    renderCurrent();
  };
  map.addEventListener("pointerup", end);
  map.addEventListener("pointercancel", end);

  $("#zoom-in").addEventListener("click", () => {
    const r = map.getBoundingClientRect();
    zoomAt(0.72, r.left + r.width / 2, r.top + r.height / 2);
  });
  $("#zoom-out").addEventListener("click", () => {
    const r = map.getBoundingClientRect();
    zoomAt(1.38, r.left + r.width / 2, r.top + r.height / 2);
  });
  $("#zoom-reset").addEventListener("click", resetCamera);
  $("#time-older").addEventListener("click", () => shiftTime(-1));
  $("#time-newer").addEventListener("click", () => shiftTime(1));
}
async function formatBdr() {
  const button = $("#format-bdr");
  const confirmation = window.prompt("Esta operação apaga todos os nódulos persistidos. Digite FORMATAR para confirmar.");
  if (confirmation !== "FORMATAR") return;
  button.disabled = true;
  const old = button.textContent;
  button.textContent = "Formatando…";
  try {
    const response = await fetch("/api/server/v1/format-bdr", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify({ confirm: confirmation }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || body.error || `HTTP ${response.status}`);
    selectedEpisodeId = null;
    $("#inspector").hidden = true;
    $("#inspector-empty").hidden = false;
    temporal.total = 0; temporal.offset = 0; temporal.limit = temporal.maxLimit;
    Object.assign(camera, { x: 0, y: 0, width: WORLD.width, height: WORLD.height });
    await loadWindow(0, temporal.minLimit);
    window.alert(`BDR formatado. Episódios removidos: ${body.upstream?.removed_episodes ?? 0}.`);
  } catch (error) {
    window.alert(`Falha ao formatar BDR: ${error.message}`);
  } finally {
    button.disabled = false;
    button.textContent = old;
  }
}

async function start() {
  try {
    const [health, observation, probe, serverCapabilities] = await Promise.all([
      fetch("/api/bdr-explorer/v1/health", { cache: "no-store" }).then((r) => r.json()),
      fetch("/api/bdr-explorer/v1/observation", { cache: "no-store" }).then((r) => r.json()),
      fetchSnapshot(0, 1),
      fetch("/api/server/v1/capabilities", { cache: "no-store" }).then((r) => r.ok ? r.json() : ({})),
    ]);
    $("#health").textContent = health.status === "ok" ? "BDR conectado" : "estado desconhecido";
    $("#version").textContent = "BDR live";
    renderCapabilities(observation);
    temporal.total = Number(probe.window?.total ?? probe.statistics?.records ?? 0);
    const initialLimit = Math.min(temporal.maxLimit, Math.max(1, temporal.total || temporal.minLimit));
    const initialOffset = Math.max(0, temporal.total - initialLimit);
    bindNavigation();
    $("#search").addEventListener("input", renderCurrent);
    const formatButton = $("#format-bdr");
    if (serverCapabilities.format_bdr === true) {
      formatButton.addEventListener("click", formatBdr);
    } else {
      formatButton.disabled = true;
      formatButton.title = "Aguardando contrato administrativo seguro do BDR";
      formatButton.textContent = "Formatar BDR · indisponível";
    }
    await loadWindow(initialOffset, initialLimit);
  } catch (error) {
    $("#health").textContent = "falha de conexão";
    $("#viewport-state").textContent = error.message;
    console.error(error);
  }
}
start();
