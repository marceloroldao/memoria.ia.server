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
    proxy_timeout_seconds: float = 10.0
    max_request_bytes: int = 10 * 1024 * 1024

    @classmethod
    def from_env(cls) -> "ShellConfig":
        return cls(
            host=os.getenv("MEMORIA_SERVER_HOST", cls.host),
            port=int(os.getenv("MEMORIA_SERVER_PORT", str(cls.port))),
            memoria_api_url=os.getenv("MEMORIA_API_URL", cls.memoria_api_url).rstrip("/"),
            bdr_explorer_url=os.getenv("BDR_EXPLORER_URL", cls.bdr_explorer_url).rstrip("/"),
            proxy_timeout_seconds=float(
                os.getenv("MEMORIA_SERVER_PROXY_TIMEOUT", str(cls.proxy_timeout_seconds))
            ),
            max_request_bytes=int(
                os.getenv("MEMORIA_SERVER_MAX_REQUEST_BYTES", str(cls.max_request_bytes))
            ),
        )
