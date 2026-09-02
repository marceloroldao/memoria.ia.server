"""Small provider gateway and persistent model catalog for Memoria.ia Server."""

from __future__ import annotations

from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
import hmac
import json
import os
from pathlib import Path
import re
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return (normalized[:48] or "model") + "-" + uuid4().hex[:6]


DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "llama": "http://llama:8080/v1",
}


class GatewayError(RuntimeError):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


class ModelStore:
    FORMAT = "memoria.ia-model-catalog-v1"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.catalog_path = self.root / "models.json"
        self.secrets_path = self.root / "model-secrets.json"
        self._lock = Lock()
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _read(path: Path) -> dict:
        if not path.exists():
            return {}
        value = json.loads(path.read_text("utf-8"))
        if not isinstance(value, dict):
            raise GatewayError(500, f"invalid storage file: {path.name}")
        return value

    def _write(self, path: Path, value: dict, *, secret: bool) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        mode = 0o600 if secret else 0o640
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            os.chmod(path, mode)
        finally:
            temporary.unlink(missing_ok=True)

    def _state(self) -> tuple[dict, dict]:
        catalog = self._read(self.catalog_path)
        catalog.setdefault("format", self.FORMAT)
        catalog.setdefault("active_profile_id", None)
        catalog.setdefault("memoria_gateway_configured", False)
        catalog.setdefault("profiles", {})
        secrets = self._read(self.secrets_path)
        secrets.setdefault("profiles", {})
        return catalog, secrets

    @staticmethod
    def _public(profile: dict, secret: dict | None, active_id: str | None) -> dict:
        return {
            **profile,
            "active": profile["id"] == active_id,
            "credential_configured": bool((secret or {}).get("api_key"))
            if profile["provider"] in {"openai", "gemini"}
            else None,
        }

    def list_public(self) -> dict:
        with self._lock:
            catalog, secrets = self._state()
            active = catalog.get("active_profile_id")
            profiles = [
                self._public(profile, secrets["profiles"].get(profile_id), active)
                for profile_id, profile in catalog["profiles"].items()
            ]
        profiles.sort(key=lambda item: (not item["active"], item["name"].casefold()))
        return {"schema": self.FORMAT, "active_profile_id": active, "profiles": profiles}

    def save(self, payload: dict, profile_id: str | None = None) -> dict:
        provider = str(payload.get("provider", "")).strip().lower()
        if provider not in DEFAULT_BASE_URLS:
            raise GatewayError(422, "provider must be one of: openai, gemini, llama")
        name = str(payload.get("name", "")).strip()
        model = str(payload.get("model", "")).strip()
        if not name or not model:
            raise GatewayError(422, "name and model are required")
        base_url = str(payload.get("base_url") or DEFAULT_BASE_URLS[provider]).strip().rstrip("/")
        if not base_url.startswith(("http://", "https://")):
            raise GatewayError(422, "base_url must use http or https")

        with self._lock:
            catalog, secrets = self._state()
            profiles = catalog["profiles"]
            if profile_id is None:
                profile_id = slug(name)
                created_at = now()
            else:
                if profile_id not in profiles:
                    raise GatewayError(404, "model profile not found")
                created_at = profiles[profile_id]["created_at"]
            profile = {
                "id": profile_id,
                "name": name,
                "provider": provider,
                "model": model,
                "base_url": base_url,
                "created_at": created_at,
                "updated_at": now(),
            }
            profiles[profile_id] = profile
            secret = secrets["profiles"].setdefault(profile_id, {})
            if "api_key" in payload and payload.get("api_key") is not None:
                supplied = str(payload.get("api_key", "")).strip()
                if not supplied and provider in {"openai", "gemini"}:
                    raise GatewayError(422, "api_key cannot be blank")
                secret["api_key"] = supplied
            if provider in {"openai", "gemini"} and not secret.get("api_key"):
                raise GatewayError(422, "api_key is required for this provider")
            if provider == "llama":
                secret.pop("api_key", None)
            self._write(self.catalog_path, catalog, secret=False)
            self._write(self.secrets_path, secrets, secret=True)
            return self._public(profile, secret, catalog.get("active_profile_id"))

    def activate(self, profile_id: str) -> dict:
        with self._lock:
            catalog, secrets = self._state()
            profile = catalog["profiles"].get(profile_id)
            if profile is None:
                raise GatewayError(404, "model profile not found")
            catalog["active_profile_id"] = profile_id
            self._write(self.catalog_path, catalog, secret=False)
            return self._public(profile, secrets["profiles"].get(profile_id), profile_id)

    def delete(self, profile_id: str) -> None:
        with self._lock:
            catalog, secrets = self._state()
            if profile_id not in catalog["profiles"]:
                raise GatewayError(404, "model profile not found")
            if catalog.get("active_profile_id") == profile_id:
                raise GatewayError(409, "activate another model before deleting this one")
            catalog["profiles"].pop(profile_id, None)
            secrets["profiles"].pop(profile_id, None)
            self._write(self.catalog_path, catalog, secret=False)
            self._write(self.secrets_path, secrets, secret=True)

    def active_private(self) -> tuple[dict, str | None] | None:
        with self._lock:
            catalog, secrets = self._state()
            profile_id = catalog.get("active_profile_id")
            if not profile_id:
                return None
            profile = catalog["profiles"].get(profile_id)
            if not profile:
                return None
            api_key = (secrets["profiles"].get(profile_id) or {}).get("api_key")
            return dict(profile), api_key

    def gateway_configured(self) -> bool:
        with self._lock:
            catalog, _ = self._state()
            return bool(catalog.get("memoria_gateway_configured"))

    def mark_gateway_configured(self) -> None:
        with self._lock:
            catalog, _ = self._state()
            catalog["memoria_gateway_configured"] = True
            self._write(self.catalog_path, catalog, secret=False)


def request_json(url: str, payload: dict, headers: dict[str, str], timeout: float) -> tuple[int, dict]:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
            detail = body.get("detail") or body.get("error") or raw
        except json.JSONDecodeError:
            detail = raw
        raise GatewayError(502, f"provider request failed: {detail}") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise GatewayError(502, "provider unavailable") from error


def openai_response(text: str, model: str, input_tokens: int | None, output_tokens: int | None) -> dict:
    return {
        "id": "gateway-" + uuid4().hex,
        "object": "response",
        "model": model,
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


def gemini_to_openai(data: dict, model: str) -> dict:
    chunks: list[str] = []
    for candidate in data.get("candidates", []):
        content = candidate.get("content") if isinstance(candidate, dict) else None
        for part in (content or {}).get("parts", []):
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                chunks.append(part["text"])
        if chunks:
            break
    if not chunks:
        raise GatewayError(502, "Gemini response did not contain text")
    usage = data.get("usageMetadata") or {}
    return openai_response(
        "".join(chunks),
        model,
        usage.get("promptTokenCount"),
        usage.get("candidatesTokenCount"),
    )


def llama_to_openai(data: dict, model: str) -> dict:
    choices = data.get("choices") or []
    message = choices[0].get("message") if choices and isinstance(choices[0], dict) else None
    text = (message or {}).get("content")
    if not isinstance(text, str):
        raise GatewayError(502, "Llama response did not contain message content")
    usage = data.get("usage") or {}
    return openai_response(text, model, usage.get("prompt_tokens"), usage.get("completion_tokens"))


class GatewayHandler(BaseHTTPRequestHandler):
    store: ModelStore
    admin_key: str
    runtime_key: str
    memoria_url: str
    memoria_key: str
    timeout: float

    def write_json(self, status: int, payload: object) -> None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise GatewayError(400, "invalid content length") from error
        if length < 1 or length > 1_000_000:
            raise GatewayError(400, "invalid request size")
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GatewayError(400, "invalid JSON") from error
        if not isinstance(body, dict):
            raise GatewayError(400, "JSON object required")
        return body

    def require_admin(self) -> None:
        supplied = self.headers.get("X-Model-Gateway-Key", "")
        if not supplied or not hmac.compare_digest(supplied, self.admin_key):
            raise GatewayError(401, "invalid gateway credentials")

    def ensure_memoria_gateway(self) -> bool:
        payload = {"provider": "openai", "model": "gateway-active", "api_key": self.runtime_key}
        request_json(
            self.memoria_url + "/api/v1/admin/configuration/llm",
            payload,
            {"X-Memoria-Key": self.memoria_key},
            self.timeout,
        )
        return True

    def route_provider(self, incoming: dict) -> dict:
        active = self.store.active_private()
        if active is None:
            authorization = self.headers.get("Authorization", "")
            if not authorization.startswith("Bearer "):
                raise GatewayError(401, "missing provider credential")
            body = dict(incoming)
            _, result = request_json(
                "https://api.openai.com/v1/responses",
                body,
                {"Authorization": authorization},
                self.timeout,
            )
            return result

        authorization = self.headers.get("Authorization", "")
        if not hmac.compare_digest(authorization, f"Bearer {self.runtime_key}"):
            raise GatewayError(401, "invalid model gateway runtime credential")
        profile, api_key = active
        provider = profile["provider"]
        model = profile["model"]
        prompt = incoming.get("input")
        if not isinstance(prompt, str) or not prompt:
            raise GatewayError(422, "input text is required")
        if provider == "openai":
            body = dict(incoming)
            body["model"] = model
            _, result = request_json(
                profile["base_url"] + "/responses",
                body,
                {"Authorization": f"Bearer {api_key}"},
                self.timeout,
            )
            return result
        if provider == "gemini":
            _, result = request_json(
                profile["base_url"] + f"/models/{model.removeprefix('models/')}:generateContent",
                {"contents": [{"role": "user", "parts": [{"text": prompt}]}]},
                {"x-goog-api-key": str(api_key)},
                self.timeout,
            )
            return gemini_to_openai(result, model)
        _, result = request_json(
            profile["base_url"] + "/chat/completions",
            {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False},
            {},
            self.timeout,
        )
        return llama_to_openai(result, model)

    def dispatch(self) -> None:
        path = urlsplit(self.path).path
        try:
            if path == "/health" and self.command == "GET":
                self.write_json(200, {"status": "ok", "active": self.store.list_public()["active_profile_id"]})
                return
            if path == "/v1/responses" and self.command == "POST":
                self.write_json(200, self.route_provider(self.read_json()))
                return
            if path == "/v1/models" and self.command == "GET":
                active = self.store.active_private()
                model = active[0]["model"] if active else "gateway-fallback"
                self.write_json(200, {"object": "list", "data": [{"id": model, "object": "model"}]})
                return

            if not path.startswith("/admin/models"):
                raise GatewayError(404, "route not found")
            self.require_admin()
            suffix = path[len("/admin/models"):].strip("/")
            parts = suffix.split("/") if suffix else []
            if not parts and self.command == "GET":
                self.write_json(200, self.store.list_public())
                return
            if not parts and self.command == "POST":
                self.write_json(201, {"profile": self.store.save(self.read_json())})
                return
            if len(parts) == 1 and self.command == "PUT":
                self.write_json(200, {"profile": self.store.save(self.read_json(), parts[0])})
                return
            if len(parts) == 1 and self.command == "DELETE":
                self.store.delete(parts[0])
                self.write_json(200, {"deleted": True, "profile_id": parts[0]})
                return
            if len(parts) == 2 and parts[1] == "activate" and self.command == "POST":
                profile = self.store.activate(parts[0])
                restart_required = not self.store.gateway_configured()
                if restart_required:
                    self.ensure_memoria_gateway()
                    self.store.mark_gateway_configured()
                self.write_json(
                    200,
                    {
                        "active": True,
                        "profile": profile,
                        "restart_required": restart_required,
                        "message": "Reinicie Memoria.ia uma vez para concluir a migração ao gateway.",
                    },
                )
                return
            raise GatewayError(405, "method not allowed")
        except GatewayError as error:
            self.write_json(error.status, {"error": "gateway_error", "detail": error.detail})
        except Exception as error:
            print(f"[model-gateway] unexpected error: {error}")
            self.write_json(500, {"error": "gateway_internal_error"})

    do_GET = dispatch
    do_POST = dispatch
    do_PUT = dispatch
    do_DELETE = dispatch

    def log_message(self, format: str, *args: object) -> None:
        print("[model-gateway] " + (format % args))


def main() -> None:
    host = os.getenv("MODEL_GATEWAY_HOST", "0.0.0.0")
    port = int(os.getenv("MODEL_GATEWAY_PORT", "8090"))
    GatewayHandler.store = ModelStore(os.getenv("MODEL_GATEWAY_DATA_DIR", "/data"))
    GatewayHandler.admin_key = os.environ["MODEL_GATEWAY_ADMIN_KEY"]
    GatewayHandler.runtime_key = os.environ["MODEL_GATEWAY_RUNTIME_KEY"]
    GatewayHandler.memoria_url = os.getenv("MEMORIA_API_URL", "http://memoria:8080").rstrip("/")
    GatewayHandler.memoria_key = os.environ["MEMORIA_API_KEY"]
    GatewayHandler.timeout = float(os.getenv("MODEL_GATEWAY_TIMEOUT", "120"))
    server = ThreadingHTTPServer((host, port), GatewayHandler)
    print(f"Memoria.ia model gateway: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
