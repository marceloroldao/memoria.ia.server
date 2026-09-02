const form = document.getElementById("loginForm");
const error = document.getElementById("error");
const button = document.getElementById("submitButton");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  error.textContent = "";
  button.disabled = true;
  button.textContent = "Entrando…";
  try {
    const response = await fetch("/api/server/v1/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: document.getElementById("username").value,
        password: document.getElementById("password").value,
      }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 429) throw new Error("Muitas tentativas. Aguarde alguns minutos.");
      throw new Error(body.error === "invalid_credentials" ? "Usuário ou senha inválidos." : "Não foi possível entrar.");
    }
    window.location.replace("/");
  } catch (exception) {
    error.textContent = exception.message;
  } finally {
    button.disabled = false;
    button.textContent = "Entrar";
  }
});
