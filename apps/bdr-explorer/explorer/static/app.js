const NS = "http://www.w3.org/2000/svg";
const $ = (selector) => document.querySelector(selector);
let snapshotCache = null;

function svg(name, attrs = {}) {
  const el = document.createElementNS(NS, name);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
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
  const entries = [
    ["registros", stats.records ?? 0],
    ["buckets", stats.occupied_buckets ?? 0],
    ["carga", Number(stats.load_factor ?? 0).toFixed(5)],
    ["fases", stats.phase_slots ?? 0],
  ];
  for (const item of entries) root.appendChild(metric(...item));
}

function renderCapabilities(observation) {
  const root = $("#capabilities");
  root.replaceChildren();
  for (const [name, capability] of Object.entries(observation.capabilities ?? {})) {
    const row = document.createElement("div");
    row.className = `capability ${capability.available ? "available" : "unavailable"}`;
    const label = document.createElement("span");
    label.textContent = name.replaceAll("_", " ");
    const state = document.createElement("small");
    state.textContent = capability.available ? "disponível" : "aguarda contrato público";
    if (capability.reason) state.title = capability.reason;
    row.append(label, state);
    root.appendChild(row);
  }
}

function showNode(node, group) {
  document.querySelectorAll(".node.active").forEach((item) => item.classList.remove("active"));
  group.classList.add("active");
  $("#inspector-empty").hidden = true;
  const panel = $("#inspector");
  panel.hidden = false;
  const fields = [
    ["BDR record ID", node.id],
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
    dd.textContent = String(value);
    panel.append(dt, dd);
  }
}

function renderMap(nodes, stats) {
  const map = $("#map");
  map.replaceChildren();
  const cx = 550;
  const cy = 345;
  const maxRadius = 285;
  const bucketCount = Math.max(Number(stats.bucket_count ?? 1), 1);

  for (const r of [72, 142, 214, 285]) map.appendChild(svg("circle", { cx, cy, r, class: "orbit" }));
  map.appendChild(svg("line", { x1: 120, y1: cy, x2: 980, y2: cy, class: "axis" }));
  map.appendChild(svg("line", { x1: cx, y1: 40, x2: cx, y2: 650, class: "axis" }));
  map.appendChild(svg("circle", { cx, cy, r: 4, fill: "rgba(159,240,207,.92)" }));

  for (const node of nodes) {
    const normalizedRho = Math.min(Math.max(Number(node.rho_R) / Math.max(bucketCount - 1, 1), 0), 1);
    const radius = 28 + normalizedRho * (maxRadius - 28);
    const angle = Number(node.theta) - Math.PI / 2;
    const x = cx + Math.cos(angle) * radius;
    const y = cy + Math.sin(angle) * radius;
    const size = 5 + Math.min(Math.max(Number(node.f_nu), 0), 1) * 8;
    const group = svg("g", { class: "node", tabindex: "0", "aria-label": `Estado BDR ${node.id}` });
    group.appendChild(svg("circle", { cx: x.toFixed(2), cy: y.toFixed(2), r: size.toFixed(2) }));

    if (nodes.length <= 80) {
      const label = svg("text", { x: (x + size + 5).toFixed(2), y: (y + 3).toFixed(2), class: "node-label" });
      label.textContent = `#${node.id}`;
      group.appendChild(label);
    }

    group.addEventListener("click", () => showNode(node, group));
    group.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") showNode(node, group);
    });
    map.appendChild(group);
  }
}

function matches(node, query) {
  if (!query) return true;
  const haystack = [node.id, node.rho_R, node.phi, node.fingerprint, node.payload_preview]
    .map((value) => String(value ?? "").toLowerCase())
    .join(" ");
  return haystack.includes(query.toLowerCase());
}

function applySearch() {
  if (!snapshotCache) return;
  const query = $("#search").value.trim();
  renderMap(snapshotCache.nodes.filter((node) => matches(node, query)), snapshotCache.statistics);
}

async function start() {
  try {
    const [health, snapshot, observation] = await Promise.all([
      fetch("/api/health", { cache: "no-store" }).then((r) => r.json()),
      fetch("/api/snapshot", { cache: "no-store" }).then((r) => r.json()),
      fetch("/api/observation", { cache: "no-store" }).then((r) => r.json()),
    ]);
    $("#health").textContent = health.status === "ok" ? "BDR conectado" : "estado desconhecido";
    snapshotCache = snapshot;
    $("#version").textContent = `BDR ${snapshot.bdr_version}`;
    renderMetrics(snapshot.statistics);
    renderCapabilities(observation);
    renderMap(snapshot.nodes, snapshot.statistics);
    $("#search").addEventListener("input", applySearch);
  } catch (error) {
    $("#health").textContent = "falha de conexão";
    console.error(error);
  }
}

start();
