"""Runtime configuration for the composition shell."""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class ShellConfig:
    host: str = "127.0.0.1"
    port: int = 8780
    memoria_api_url: str = "http://127.0.0.1:8000"
    bdr_explorer_url: str = "http://127.0.0.1:8765"
    model_gateway_url: str = "http://127.0.0.1:8090"
    model_gateway_key: str = ""
    proxy_timeout_seconds: float = 10.0
    max_request_bytes: int = 10 * 1024 * 1024
    admin_username: str = "admin"
    admin_password: str = ""
    session_hours: int = 8
    cookie_secure: bool = False
    memoria_api_key: str = ""

    @classmethod
    def from_env(cls) -> "ShellConfig":
        return cls(
            host=os.getenv("MEMORIA_SERVER_HOST", cls.host),
            port=int(os.getenv("MEMORIA_SERVER_PORT", str(cls.port))),
            memoria_api_url=os.getenv("MEMORIA_API_URL", cls.memoria_api_url).rstrip("/"),
            bdr_explorer_url=os.getenv("BDR_EXPLORER_URL", cls.bdr_explorer_url).rstrip("/"),
            model_gateway_url=os.getenv("MODEL_GATEWAY_URL", cls.model_gateway_url).rstrip("/"),
            model_gateway_key=os.getenv("MODEL_GATEWAY_ADMIN_KEY", cls.model_gateway_key),
            proxy_timeout_seconds=float(
                os.getenv("MEMORIA_SERVER_PROXY_TIMEOUT", str(cls.proxy_timeout_seconds))
            ),
            max_request_bytes=int(
                os.getenv("MEMORIA_SERVER_MAX_REQUEST_BYTES", str(cls.max_request_bytes))
            ),
            admin_username=os.getenv("MEMORIA_SERVER_ADMIN_USER", cls.admin_username),
            admin_password=os.getenv("MEMORIA_SERVER_ADMIN_PASSWORD", cls.admin_password),
            session_hours=int(os.getenv("MEMORIA_SERVER_SESSION_HOURS", str(cls.session_hours))),
            cookie_secure=os.getenv("MEMORIA_SERVER_COOKIE_SECURE", "false").lower()
            in {"1", "true", "yes", "on"},
            memoria_api_key=os.getenv("MEMORIA_API_KEY", cls.memoria_api_key),
        )
