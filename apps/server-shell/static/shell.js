const $ = (id) => document.getElementById(id);

function setState(id, state) {
  const element = $(id);
  element.textContent = state === "online" ? "online" : state === "offline" ? "indisponível" : state;
  element.dataset.state = state;
}

async function refreshHealth() {
  try {
    const response = await fetch("/api/server/v1/health", { cache: "no-store" });
    if (!response.ok) throw new Error("health request failed");
    const health = await response.json();
    $("healthText").textContent = health.status === "online" ? "todos os serviços online" : "operação parcial";
    $("healthDot").dataset.state = health.status;
    setState("memoriaState", health.components.memoria.status);
    setState("bdrState", health.components.bdr_explorer.status);
    $("deviceState").textContent = `${health.devices?.total ?? 0} dispositivo(s)`;
    $("deviceState").dataset.state = "online";
  } catch {
    $("healthText").textContent = "shell sem telemetria";
    $("healthDot").dataset.state = "offline";
    setState("memoriaState", "offline");
    setState("bdrState", "offline");
    $("deviceState").textContent = "indisponível";
    $("deviceState").dataset.state = "offline";
  }
}

refreshHealth();
setInterval(refreshHealth, 15000);

document.getElementById("logout").addEventListener("click", async () => {
  try {
    await fetch("/api/server/v1/logout", { method: "POST" });
  } finally {
    window.location.replace("/login");
  }
});
