"""Server-side autonomous relation tests for Memoria.ia."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import re
from threading import Event, Lock, Thread
import time
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


PREFIX = "/api/server/v1/autotests"


class UpstreamError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value).casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def extract_json_object(text: str) -> dict[str, object]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("O agente GPT não retornou um cenário JSON válido")


def evaluate_expected(expected_terms: list[str], response: object) -> bool:
    normalized = _normalize(json.dumps(response, ensure_ascii=False, sort_keys=True))
    return bool(expected_terms) and all(_normalize(term) in normalized for term in expected_terms)


class MemoriaClient:
    def __init__(self, base_url: str, api_key: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            self.base_url + path,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json", "X-Memoria-Key": self.api_key},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
                if not isinstance(body, dict):
                    raise UpstreamError("Resposta inválida da Memoria.ia")
                return body
        except HTTPError as error:
            try:
                body = json.loads(error.read().decode("utf-8"))
                detail = body.get("detail") or body.get("error")
            except Exception:
                detail = None
            raise UpstreamError(str(detail or f"Memoria.ia retornou HTTP {error.code}")) from error
        except TimeoutError as error:
            raise UpstreamError(
                f"Tempo limite da Memoria.ia excedido durante o teste ({self.timeout:.0f}s)"
            ) from error
        except URLError as error:
            raise UpstreamError("Memoria.ia indisponível durante o teste") from error
        except json.JSONDecodeError as error:
            raise UpstreamError("Memoria.ia retornou uma resposta inválida durante o teste") from error


@dataclass
class TestRun:
    run_id: str
    cycles: int
    delay_ms: int
    session_id: str
    status: str = "running"
    created_at: str = field(default_factory=_now)
    finished_at: str | None = None
    passed: int = 0
    failed: int = 0
    completed_cycles: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    events: list[dict[str, object]] = field(default_factory=list)
    pause: Event = field(default_factory=Event, repr=False)
    stop: Event = field(default_factory=Event, repr=False)

    def __post_init__(self) -> None:
        self.pause.set()


class AutonomousTestManager:
    """Owns bounded in-memory test runs and streams snapshots to the UI."""

    def __init__(self, config) -> None:
        self.client = MemoriaClient(
            config.memoria_api_url,
            config.memoria_api_key,
            max(config.autotest_timeout_seconds, config.proxy_timeout_seconds),
        )
        self._runs: dict[str, TestRun] = {}
        self._lock = Lock()

    def _event(
        self,
        run: TestRun,
        speaker: str,
        text: str,
        *,
        kind: str = "message",
        details: object | None = None,
    ) -> None:
        with self._lock:
            event: dict[str, object] = {
                "seq": len(run.events) + 1,
                "time": _now(),
                "speaker": speaker,
                "kind": kind,
                "text": text,
            }
            if details is not None:
                event["details"] = details
            run.events.append(event)

    def _scenario_prompt(self, cycle: int, previous: list[dict[str, object]]) -> str:
        history = [str(item.get("text", "")) for item in previous[-4:]]
        return (
            "Você é um agente de teste da Memoria.ia. Crie UM pequeno cenário factual "
            "em português, diferente dos anteriores, com relações simples e verificáveis. "
            "Pode testar atributos, posse, localização, parentesco, sequência ou correção. "
            "Responda exclusivamente com JSON válido no formato: "
            '{"assertion":"frase que ensina os fatos","question":"pergunta sobre os fatos",'
            '"expected_terms":["termos obrigatórios na resposta"]}. '
            f"Ciclo: {cycle}. Cenários recentes: {json.dumps(history, ensure_ascii=False)}"
        )

    def _generate_scenario(self, run: TestRun, cycle: int) -> dict[str, object]:
        generated = self.client.post(
            "/api/v1/chat",
            {
                "message": self._scenario_prompt(cycle, run.events),
                "mode": "baseline",
                "baseline_context": [],
                "memory_keys": [],
                "scope": {"application_id": "server-autotest", "agent_id": run.run_id},
            },
        )
        metrics = generated.get("metrics") or {}
        if isinstance(metrics, dict):
            run.input_tokens += int(metrics.get("input_tokens") or 0)
            run.output_tokens += int(metrics.get("output_tokens") or 0)
            run.estimated_cost_usd += float(metrics.get("estimated_cost_usd") or 0.0)
        scenario = extract_json_object(str(generated.get("text", "")))
        assertion = str(scenario.get("assertion", "")).strip()
        question = str(scenario.get("question", "")).strip()
        expected = scenario.get("expected_terms")
        if not assertion or not question or not isinstance(expected, list) or not expected:
            raise ValueError("O cenário do agente GPT está incompleto")
        return {
            "assertion": assertion,
            "question": question,
            "expected_terms": [str(item) for item in expected if str(item).strip()][:12],
            "provider": metrics.get("provider") if isinstance(metrics, dict) else None,
            "model": metrics.get("model") if isinstance(metrics, dict) else None,
        }

    def _run(self, run: TestRun) -> None:
        self._event(run, "system", f"Teste autônomo iniciado: {run.cycles} ciclos.", kind="status")
        try:
            for cycle in range(1, run.cycles + 1):
                run.pause.wait()
                if run.stop.is_set():
                    break
                scenario = self._generate_scenario(run, cycle)
                self._event(
                    run,
                    "agent",
                    str(scenario["assertion"]),
                    details={"cycle": cycle, "provider": scenario.get("provider"), "model": scenario.get("model")},
                )
                ingested = self.client.post(
                    "/api/v1/conversation/ingest",
                    {
                        "role": "user",
                        "text": scenario["assertion"],
                        "session_id": run.session_id,
                        "order": cycle * 2,
                    },
                )
                relations = ingested.get("relations") or []
                relation_count = len(relations) if isinstance(relations, list) else 0
                self._event(
                    run,
                    "memoria",
                    f"Registrei {relation_count} relação(ões).",
                    kind="ingest",
                    details=ingested,
                )
                self._event(run, "agent", str(scenario["question"]), kind="question")
                resolved = self.client.post(
                    "/api/v1/conversation/resolve",
                    {"query": scenario["question"], "session_id": run.session_id},
                )
                answer = str(resolved.get("selected_context") or "Relação não encontrada.")
                self._event(run, "memoria", answer, kind="answer", details=resolved)
                passed = str(resolved.get("status")) == "HIT" and evaluate_expected(
                    list(scenario["expected_terms"]), resolved
                )
                if passed:
                    run.passed += 1
                    verdict = "✅ Relações recuperadas corretamente."
                else:
                    run.failed += 1
                    verdict = "❌ A resposta não correspondeu ao gabarito."
                self._event(
                    run,
                    "evaluator",
                    verdict,
                    kind="pass" if passed else "fail",
                    details={"expected_terms": scenario["expected_terms"], "cycle": cycle},
                )
                run.completed_cycles = cycle
                if run.delay_ms and run.stop.wait(run.delay_ms / 1000):
                    break
            run.status = "stopped" if run.stop.is_set() else "completed"
        except Exception as error:
            run.status = "error"
            self._event(run, "system", f"Teste interrompido: {error}", kind="error")
        finally:
            run.finished_at = _now()
            self._event(run, "system", "Teste finalizado. Relatório disponível.", kind="status")

    def start(self, cycles: int, delay_ms: int) -> TestRun:
        cycles = max(1, min(int(cycles), 50))
        delay_ms = max(0, min(int(delay_ms), 10000))
        run_id = uuid4().hex[:12]
        run = TestRun(run_id, cycles, delay_ms, f"autotest:{run_id}")
        with self._lock:
            finished = [key for key, value in self._runs.items() if value.status not in {"running", "paused"}]
            for key in finished[:-19]:
                self._runs.pop(key, None)
            self._runs[run_id] = run
        Thread(target=self._run, args=(run,), daemon=True, name=f"autotest-{run_id}").start()
        return run

    def action(self, run_id: str, action: str) -> TestRun:
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(run_id)
        if action == "pause" and run.status == "running":
            run.pause.clear()
            run.status = "paused"
            self._event(run, "system", "Teste pausado.", kind="status")
        elif action == "resume" and run.status == "paused":
            run.status = "running"
            run.pause.set()
            self._event(run, "system", "Teste retomado.", kind="status")
        elif action == "stop" and run.status in {"running", "paused"}:
            run.status = "stopping"
            run.stop.set()
            run.pause.set()
        return run

    def snapshot(self, run_id: str, after: int = 0) -> dict[str, object]:
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(run_id)
        with self._lock:
            events = [dict(event) for event in run.events if int(event["seq"]) > after]
        total = run.passed + run.failed
        return {
            "schema": "memoria-autotest-run/v1",
            "run_id": run.run_id,
            "status": run.status,
            "cycles": run.cycles,
            "completed_cycles": run.completed_cycles,
            "summary": {
                "passed": run.passed,
                "failed": run.failed,
                "accuracy": (run.passed / total) if total else None,
                "input_tokens": run.input_tokens,
                "output_tokens": run.output_tokens,
                "estimated_cost_usd": run.estimated_cost_usd,
            },
            "created_at": run.created_at,
            "finished_at": run.finished_at,
            "events": events,
        }

    def dispatch(self, handler, path: str, query: dict[str, list[str]]) -> bool:
        if path != PREFIX and not path.startswith(PREFIX + "/"):
            return False
        suffix = path[len(PREFIX):].strip("/")
        parts = suffix.split("/") if suffix else []
        try:
            if not parts and handler.command == "POST":
                raw = handler._read_body()
                if raw is None:
                    return True
                body = json.loads(raw.decode("utf-8") or "{}")
                run = self.start(body.get("cycles", 5), body.get("delay_ms", 500))
                handler._write_json(202, self.snapshot(run.run_id))
                return True
            if len(parts) == 1 and handler.command == "GET":
                after = int((query.get("after") or ["0"])[0])
                handler._write_json(200, self.snapshot(parts[0], after))
                return True
            if len(parts) == 2 and parts[1] in {"pause", "resume", "stop"} and handler.command == "POST":
                run = self.action(parts[0], parts[1])
                handler._write_json(200, self.snapshot(run.run_id))
                return True
            if len(parts) == 2 and parts[1] == "report" and handler.command == "GET":
                handler._write_json(200, self.snapshot(parts[0]))
                return True
        except KeyError:
            handler._write_json(404, {"error": "autotest_not_found"})
            return True
        except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as error:
            handler._write_json(400, {"error": "invalid_autotest_request", "detail": str(error)})
            return True
        handler._write_json(405, {"error": "method_not_allowed"})
        return True
