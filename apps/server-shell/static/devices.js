const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, {
    cache: "no-store",
    ...options,
    headers: { "Accept": "application/json", ...(options.headers || {}) },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || body.error || `HTTP ${response.status}`);
  return body;
}

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}

function statusLabel(status) {
  return ({pending:"pendente",active:"ativo",suspended:"suspenso",revoked:"revogado"})[status] || status || "—";
}

function formatTime(value) {
  if (!value) return "nunca";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("pt-BR");
}

function renderStats(devices) {
  const counts = {total: devices.length, pending:0, active:0, suspended:0, revoked:0};
  for (const device of devices) if (device.status in counts) counts[device.status] += 1;
  const root = $("deviceStats");
  root.replaceChildren();
  for (const [label, key] of [["total","total"],["ativos","active"],["pendentes","pending"],["suspensos","suspended"],["revogados","revoked"]]) {
    const card = el("div", null, "stat-card");
    card.append(el("strong", counts[key]), el("span", label));
    root.append(card);
  }
}

function actionButton(label, action, deviceId, className = "") {
  const button = el("button", label, `device-action ${className}`.trim());
  button.type = "button";
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await api(`/api/server/v1/devices/${encodeURIComponent(deviceId)}/${action}`, {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: "{}",
      });
      await refreshAll();
    } catch (error) {
      window.alert(error.message);
      button.disabled = false;
    }
  });
  return button;
}

function renderDevices(devices) {
  renderStats(devices);
  const rows = $("deviceRows");
  rows.replaceChildren();
  if (!devices.length) {
    const tr = document.createElement("tr");
    const td = el("td", "Nenhum dispositivo neste filtro.", "muted");
    td.colSpan = 6;
    tr.append(td); rows.append(tr); return;
  }
  for (const device of devices) {
    const tr = document.createElement("tr");

    const identity = document.createElement("td");
    identity.append(el("strong", device.name), el("small", device.device_id));
    const type = el("td", device.type);
    const status = document.createElement("td");
    status.append(el("span", statusLabel(device.status), `status-chip ${device.status}`));
    const seen = el("td", formatTime(device.last_seen));
    const caps = document.createElement("td");
    const cap = device.capabilities || {};
    const pieces = [cap.cpu, ...(cap.models || [])].filter(Boolean);
    caps.textContent = pieces.join(" · ") || "—";

    const actions = document.createElement("td");
    actions.className = "device-actions";
    if (device.status === "pending" || device.status === "suspended") actions.append(actionButton("Aprovar", "approve", device.device_id));
    if (device.status === "active") {
      actions.append(actionButton("Heartbeat", "heartbeat", device.device_id));
      actions.append(actionButton("Suspender", "suspend", device.device_id));
    }
    if (device.status !== "revoked") actions.append(actionButton("Revogar", "revoke", device.device_id, "danger"));
    tr.append(identity, type, status, seen, caps, actions);
    rows.append(tr);
  }
}

function renderAudit(events) {
  const root = $("auditList");
  root.replaceChildren();
  if (!events.length) {
    root.append(el("p", "Nenhum evento registrado.", "muted"));
    return;
  }
  for (const event of [...events].reverse()) {
    const row = el("div", null, "audit-row");
    const head = el("div");
    head.append(el("strong", event.action), el("span", ` #${event.sequence}`));
    row.append(head, el("small", `${formatTime(event.timestamp)} · ${event.target || "server"}`));
    root.append(row);
  }
}

async function refreshAll() {
  const status = $("statusFilter").value;
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  const [identity, devices, audit] = await Promise.all([
    api("/api/server/v1/server/identity"),
    api("/api/server/v1/devices" + query),
    api("/api/server/v1/audit?limit=30"),
  ]);
  $("serverId").textContent = identity.server_id;
  renderDevices(devices.devices || []);
  renderAudit(audit.events || []);
}

$("registerDevice").addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = $("registerMessage");
  message.textContent = "Registrando…";
  const model = $("deviceModel").value.trim();
  const payload = {
    name: $("deviceName").value.trim(),
    type: $("deviceType").value,
    public_key: $("devicePublicKey").value.trim(),
    capabilities: {
      cpu: $("deviceCpu").value.trim(),
      models: model ? [model] : [],
    },
    versions: {},
    groups: [],
    permissions: [],
  };
  try {
    const result = await api("/api/server/v1/devices/register", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify(payload),
    });
    message.textContent = result.created ? "Dispositivo registrado como pendente." : "Esta chave pública já estava registrada.";
    if (result.created) event.target.reset();
    await refreshAll();
  } catch (error) {
    message.textContent = error.message;
  }
});

$("statusFilter").addEventListener("change", () => refreshAll().catch((error) => window.alert(error.message)));
$("refreshDevices").addEventListener("click", () => refreshAll().catch((error) => window.alert(error.message)));
$("logout").addEventListener("click", async () => {
  try { await fetch("/api/server/v1/logout", {method:"POST"}); }
  finally { window.location.replace("/login"); }
});

refreshAll().catch((error) => {
  $("deviceRows").replaceChildren();
  const tr = document.createElement("tr");
  const td = el("td", error.message, "muted"); td.colSpan = 6; tr.append(td); $("deviceRows").append(tr);
});
