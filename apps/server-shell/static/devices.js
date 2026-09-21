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
  return ({
    pending:"pendente", active:"ativo", suspended:"suspenso", revoked:"revogado",
    consumed:"consumido", expired:"expirado", claiming:"processando",
  })[status] || status || "—";
}

function formatTime(value) {
  if (!value) return "nunca";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("pt-BR");
}

function permissionText(device) {
  const values = Array.isArray(device.permissions) ? device.permissions : [];
  return values.length ? values.join(" · ") : "nenhuma";
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

function permissionsButton(device) {
  const button = el("button", "Permissões", "device-action");
  button.type = "button";
  button.addEventListener("click", async () => {
    const current = Array.isArray(device.permissions) ? device.permissions.join(", ") : "";
    const raw = window.prompt(
      "Permissões separadas por vírgula. Remover uma permissão tem efeito imediato no dispositivo autenticado.",
      current,
    );
    if (raw === null) return;
    const permissions = raw.split(",").map((item) => item.trim()).filter(Boolean);
    button.disabled = true;
    try {
      await api(`/api/server/v1/devices/${encodeURIComponent(device.device_id)}/permissions`, {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({permissions}),
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
    td.colSpan = 8;
    tr.append(td); rows.append(tr); return;
  }
  for (const device of devices) {
    const tr = document.createElement("tr");

    const identity = document.createElement("td");
    identity.append(el("strong", device.name), el("small", device.device_id));
    const type = el("td", device.type);
    const status = document.createElement("td");
    status.append(el("span", statusLabel(device.status), `status-chip ${device.status}`));
    const certificate = document.createElement("td");
    certificate.append(el("span", device.certificate_status || "not_issued", `status-chip ${device.certificate_status || "pending"}`));
    const permissions = el("td", permissionText(device), "permission-cell");
    const seen = el("td", formatTime(device.last_seen));
    const caps = document.createElement("td");
    const cap = device.capabilities || {};
    const pieces = [cap.cpu, ...(cap.models || [])].filter(Boolean);
    caps.textContent = pieces.join(" · ") || "—";

    const actions = document.createElement("td");
    actions.className = "device-actions";
    if (device.status === "pending" || device.status === "suspended") actions.append(actionButton("Aprovar", "approve", device.device_id));
    if (device.status === "active") {
      actions.append(actionButton("Heartbeat admin", "heartbeat", device.device_id));
      actions.append(actionButton("Suspender", "suspend", device.device_id));
    }
    if (device.status !== "revoked") {
      actions.append(permissionsButton(device));
      actions.append(actionButton("Revogar", "revoke", device.device_id, "danger"));
    }
    tr.append(identity, type, status, certificate, permissions, seen, caps, actions);
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

function inviteAction(label, enrollmentId, action, className = "") {
  const button = el("button", label, `device-action ${className}`.trim());
  button.type = "button";
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await api(`/api/server/v1/enrollments/${encodeURIComponent(enrollmentId)}/${action}`, {
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

function renderEnrollments(invitations) {
  const root = $("enrollmentList");
  root.replaceChildren();
  if (!invitations.length) {
    root.append(el("p", "Nenhum convite criado.", "muted"));
    return;
  }
  for (const invite of invitations.slice(0, 30)) {
    const row = el("div", null, "audit-row enrollment-row");
    const head = el("div");
    head.append(
      el("strong", invite.label || invite.enrollment_id),
      el("span", statusLabel(invite.status)),
    );
    const details = el(
      "small",
      `${invite.type || "device"} · expira ${formatTime(invite.expires_at)} · ${(invite.permissions || []).join(", ") || "sem permissões"}`,
    );
    row.append(head, details);
    if (invite.device_id) row.append(el("small", `device: ${invite.device_id}`));
    if (["active", "expired", "claiming"].includes(invite.status)) {
      const actions = el("div", null, "device-actions");
      actions.append(inviteAction("Revogar", invite.enrollment_id, "revoke", "danger"));
      row.append(actions);
    }
    root.append(row);
  }
}

async function refreshAll() {
  const status = $("statusFilter").value;
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  const [identity, authority, devices, enrollments, audit] = await Promise.all([
    api("/api/server/v1/server/identity"),
    api("/api/server/v1/device-auth/authority"),
    api("/api/server/v1/devices" + query),
    api("/api/server/v1/enrollments"),
    api("/api/server/v1/audit?limit=40"),
  ]);
  $("serverId").textContent = identity.server_id;
  $("authorityFingerprint").textContent = authority.public_key_fingerprint || "—";
  renderDevices(devices.devices || []);
  renderEnrollments(enrollments.invitations || []);
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
  };
  try {
    const result = await api("/api/server/v1/devices/register", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify(payload),
    });
    message.textContent = result.created ? "Dispositivo registrado como pendente com permissões básicas." : "Esta chave pública já estava registrada.";
    if (result.created) event.target.reset();
    await refreshAll();
  } catch (error) {
    message.textContent = error.message;
  }
});

$("createEnrollment").addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = $("enrollmentMessage");
  message.textContent = "Gerando convite…";
  $("enrollmentSecretBox").hidden = true;
  const permissionSelect = $("enrollmentPermissions");
  const permissions = [...permissionSelect.selectedOptions].map((option) => option.value);
  const group = $("enrollmentGroup").value.trim();
  const payload = {
    label: $("enrollmentLabel").value.trim(),
    type: $("enrollmentType").value,
    expires_minutes: Number($("enrollmentExpires").value),
    permissions,
    groups: group ? [group] : [],
  };
  try {
    const result = await api("/api/server/v1/enrollments", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify(payload),
    });
    $("enrollmentCode").textContent = result.enrollment_code;
    $("enrollmentSecretBox").hidden = false;
    message.textContent = "Convite criado. O código não ficará disponível novamente após sair desta tela.";
    await refreshAll();
  } catch (error) {
    message.textContent = error.message;
  }
});

$("copyEnrollmentCode").addEventListener("click", async () => {
  const code = $("enrollmentCode").textContent.trim();
  if (!code) return;
  try {
    await navigator.clipboard.writeText(code);
    $("enrollmentMessage").textContent = "Código copiado.";
  } catch {
    window.prompt("Copie o código de enrollment:", code);
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
  const td = el("td", error.message, "muted"); td.colSpan = 8; tr.append(td); $("deviceRows").append(tr);
  $("enrollmentList").replaceChildren(el("p", error.message, "muted"));
});
