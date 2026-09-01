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
    provider: ExplorerSnapshotProvider
    observation_provider: PublicBDRObservationProvider
    events: EventBuffer

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
        if path == "/api/health":
            self._json({"status": "ok", "read_only": True})
            return
        if path == "/api/snapshot":
            self._json(self.provider.snapshot())
            return
        if path == "/api/observation":
            self._json(self.observation_provider.observe().as_dict())
            return
        if path == "/api/events":
            self._json({"schema": "bdr-explorer-events/v0.1", "events": self.events.snapshot()})
            return
        super().do_GET()

    def log_message(self, format: str, *args) -> None:
        print("[explorer] " + (format % args))


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolutive DB Explorer")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--demo",
        action="store_true",
        help="run with an in-memory demonstration database",
    )
    args = parser.parse_args()

    if not args.demo:
        parser.error("v0.1 currently requires --demo; persistent read-only opening is planned for E02")

    database = build_demo_database()
    ExplorerHandler.provider = ExplorerSnapshotProvider(database)
    ExplorerHandler.observation_provider = PublicBDRObservationProvider(database)
    ExplorerHandler.events = EventBuffer()
    server = ThreadingHTTPServer((args.host, args.port), ExplorerHandler)
    print(f"Resolutive DB Explorer: http://{args.host}:{args.port}")
    print("Mode: read-only demo")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
