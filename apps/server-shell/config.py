"""Runtime configuration for the composition shell."""

from __future__ import annotations

from dataclasses import dataclass
import os


def _bool_env(name: str, default: bool) -> bool:
    return os.getenv(name, "true" if default else "false").lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ShellConfig:
    host: str = "127.0.0.1"
    port: int = 8780
    memoria_api_url: str = "http://127.0.0.1:8000"
    bdr_explorer_url: str = "http://127.0.0.1:8765"
    model_gateway_url: str = "http://127.0.0.1:8090"
    model_gateway_key: str = ""
    proxy_timeout_seconds: float = 10.0
    autotest_timeout_seconds: float = 180.0
    max_request_bytes: int = 10 * 1024 * 1024
    admin_username: str = "admin"
    admin_password: str = ""
    session_hours: int = 8
    cookie_secure: bool = False
    memoria_api_key: str = ""
    curiosity_enabled: bool = True
    curiosity_data_dir: str = "/data/curiosity"
    curiosity_interval_seconds: float = 60.0
    curiosity_max_requests_hour: int = 120
    curiosity_random_jump_rate: float = 0.10
    curiosity_stagnation_limit: int = 3
    curiosity_results_per_search: int = 5
    curiosity_http_timeout: float = 12.0
    curiosity_max_page_bytes: int = 1_500_000
    curiosity_text_limit: int = 20_000
    curiosity_novelty_threshold: float = 0.25
    curiosity_seed: int = 0
    curiosity_search_url: str = "https://html.duckduckgo.com/html/?q=QUERY"

    @classmethod
    def from_env(cls) -> "ShellConfig":
        return cls(
            host=os.getenv("MEMORIA_SERVER_HOST", cls.host),
            port=int(os.getenv("MEMORIA_SERVER_PORT", str(cls.port))),
            memoria_api_url=os.getenv("MEMORIA_API_URL", cls.memoria_api_url).rstrip("/"),
            bdr_explorer_url=os.getenv("BDR_EXPLORER_URL", cls.bdr_explorer_url).rstrip("/"),
            model_gateway_url=os.getenv("MODEL_GATEWAY_URL", cls.model_gateway_url).rstrip("/"),
            model_gateway_key=os.getenv("MODEL_GATEWAY_ADMIN_KEY", cls.model_gateway_key),
            proxy_timeout_seconds=float(os.getenv("MEMORIA_SERVER_PROXY_TIMEOUT", str(cls.proxy_timeout_seconds))),
            autotest_timeout_seconds=float(os.getenv("MEMORIA_AUTOTEST_TIMEOUT", str(cls.autotest_timeout_seconds))),
            max_request_bytes=int(os.getenv("MEMORIA_SERVER_MAX_REQUEST_BYTES", str(cls.max_request_bytes))),
            admin_username=os.getenv("MEMORIA_SERVER_ADMIN_USER", cls.admin_username),
            admin_password=os.getenv("MEMORIA_SERVER_ADMIN_PASSWORD", cls.admin_password),
            session_hours=int(os.getenv("MEMORIA_SERVER_SESSION_HOURS", str(cls.session_hours))),
            cookie_secure=_bool_env("MEMORIA_SERVER_COOKIE_SECURE", cls.cookie_secure),
            memoria_api_key=os.getenv("MEMORIA_API_KEY", cls.memoria_api_key),
            curiosity_enabled=_bool_env("MEMORIA_CURIOSITY_ENABLED", cls.curiosity_enabled),
            curiosity_data_dir=os.getenv("MEMORIA_CURIOSITY_DATA_DIR", cls.curiosity_data_dir),
            curiosity_interval_seconds=max(5.0, float(os.getenv("MEMORIA_CURIOSITY_INTERVAL_SECONDS", str(cls.curiosity_interval_seconds)))),
            curiosity_max_requests_hour=max(1, int(os.getenv("MEMORIA_CURIOSITY_MAX_REQUESTS_HOUR", str(cls.curiosity_max_requests_hour)))),
            curiosity_random_jump_rate=min(1.0, max(0.0, float(os.getenv("MEMORIA_CURIOSITY_RANDOM_JUMP_RATE", str(cls.curiosity_random_jump_rate))))),
            curiosity_stagnation_limit=max(1, int(os.getenv("MEMORIA_CURIOSITY_STAGNATION_LIMIT", str(cls.curiosity_stagnation_limit)))),
            curiosity_results_per_search=max(1, min(10, int(os.getenv("MEMORIA_CURIOSITY_RESULTS_PER_SEARCH", str(cls.curiosity_results_per_search))))),
            curiosity_http_timeout=max(3.0, float(os.getenv("MEMORIA_CURIOSITY_HTTP_TIMEOUT", str(cls.curiosity_http_timeout)))),
            curiosity_max_page_bytes=max(100_000, int(os.getenv("MEMORIA_CURIOSITY_MAX_PAGE_BYTES", str(cls.curiosity_max_page_bytes)))),
            curiosity_text_limit=max(1000, int(os.getenv("MEMORIA_CURIOSITY_TEXT_LIMIT", str(cls.curiosity_text_limit)))),
            curiosity_novelty_threshold=min(1.0, max(0.0, float(os.getenv("MEMORIA_CURIOSITY_NOVELTY_THRESHOLD", str(cls.curiosity_novelty_threshold))))),
            curiosity_seed=int(os.getenv("MEMORIA_CURIOSITY_SEED", str(cls.curiosity_seed))),
            curiosity_search_url=os.getenv("MEMORIA_CURIOSITY_SEARCH_URL", cls.curiosity_search_url),
        )
