"""Minimal standard-library web server for the Resolutive DB Explorer."""

from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlparse

from bdr import BancoDeDadosResolutivo

from .adapter import ExplorerSnapshotProvider
from .events import EventBuffer
from .live_memoria import LiveMemoriaSnapshotProvider
from .observation import PublicBDRObservationProvider


STATIC_DIR = Path(__file__).with_name("static")


def build_demo_database() -> BancoDeDadosResolutivo:
    db = BancoDeDadosResolutivo(bucket_count=1 << 10)
    samples = (
        ("memoria:identidade", "Identidade persistente do agente"),
        ("memoria:preferencia", "Preferencias e regras de contexto"),
        ("memoria:episodio:001", "Primeiro episodio observado"),
        ("memoria:episodio:002", "Segundo episodio observado"),
        ("ma2a:no:central", "No central da malha MA2A"),
        ("ma2a:no:borda:01", "No de borda local"),
        ("resolutivo:conceito:tempo", "Tempo como relacao de atualizacao"),
        ("resolutivo:conceito:trajetoria", "Trajetoria entre estados"),
    )
    db.inserir_lote(samples)
    return db


class ExplorerHandler(SimpleHTTPRequestHandler):
    provider: object
    observation_provider: object | None = None
    events: EventBuffer
    mode = "unknown"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def _json(self, payload: object, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        path = urlparse(self.path).path
        try:
            if path == "/api/health":
                self._json({"status": "ok", "read_only": True, "mode": self.mode})
                return
            if path == "/api/snapshot":
                self._json(self.provider.snapshot())
                return
            if path == "/api/observation":
                if hasattr(self.provider, "observation"):
                    self._json(self.provider.observation())
                elif self.observation_provider is not None:
                    self._json(self.observation_provider.observe().as_dict())
                else:
                    self._json({"error": "observation_unavailable"}, 503)
                return
            if path == "/api/events":
                self._json({"schema": "bdr-explorer-events/v0.1", "events": self.events.snapshot()})
                return
            super().do_GET()
        except Exception as exc:  # Explorer must fail visibly, never fabricate demo data.
            self._json({"error": "live_source_unavailable", "detail": str(exc)}, 502)

    def log_message(self, format: str, *args) -> None:
        print("[explorer] " + (format % args))


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolutive DB Explorer")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--demo", action="store_true", help="run with an in-memory demonstration database")
    parser.add_argument("--memoria-url", help="Memoria.ia base URL used as the live read-only source")
    parser.add_argument("--memoria-api-key", help="Memoria.ia administrator API key")
    args = parser.parse_args()

    if args.demo:
        database = build_demo_database()
        ExplorerHandler.provider = ExplorerSnapshotProvider(database)
        ExplorerHandler.observation_provider = PublicBDRObservationProvider(database)
        ExplorerHandler.mode = "demo"
    else:
        if not args.memoria_url or not args.memoria_api_key:
            parser.error("live mode requires --memoria-url and --memoria-api-key")
        ExplorerHandler.provider = LiveMemoriaSnapshotProvider(args.memoria_url, args.memoria_api_key)
        ExplorerHandler.observation_provider = None
        ExplorerHandler.mode = "memoria.ia-live"

    ExplorerHandler.events = EventBuffer()
    server = ThreadingHTTPServer((args.host, args.port), ExplorerHandler)
    print(f"Resolutive DB Explorer: http://{args.host}:{args.port}")
    print(f"Mode: read-only {ExplorerHandler.mode}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
