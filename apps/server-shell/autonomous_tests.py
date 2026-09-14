"""Server-side autonomous relation tests for Memoria.ia.

V2 deliberately keeps the exploration loop independent from an LLM: scenarios are
created locally, ingested as facts and resolved directly through Memoria.ia.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import random
import re
from threading import Event, Lock, Thread
import time
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


PREFIX = "/api/server/v1/autotests"
TOPICS = ("attribute", "possession", "location", "sequence", "correction", "relation")


class UpstreamError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value).casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def extract_json_object(text: str) -> dict[str, object]:
    """Backward-compatible helper kept for old test/report consumers."""
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
    raise ValueError("Nenhum objeto JSON válido foi encontrado")


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
    jump_rate: float = 0.35
    seed: int = 0
    status: str = "running"
    created_at: str = field(default_factory=_now)
    finished_at: str | None = None
    passed: int = 0
    failed: int = 0
    completed_cycles: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    jumps: int = 0
    last_topic: str | None = None
    topic_streak: int = 0
    events: list[dict[str, object]] = field(default_factory=list)
    pause: Event = field(default_factory=Event, repr=False)
    stop: Event = field(default_factory=Event, repr=False)

    def __post_init__(self) -> None:
        self.pause.set()
        if not self.seed:
            self.seed = int(self.run_id[:8], 16) if re.fullmatch(r"[0-9a-f]+", self.run_id[:8]) else 1


class CuriosityGenerator:
    """Local exploration generator with reproducible random topic jumps."""

    COLORS = ("azul", "verde", "vermelho", "preto", "branco", "amarelo")
    OBJECTS = ("caderno", "chave", "sensor", "capacete", "livro", "drone")
    PLACES = ("oficina", "garagem", "laboratório", "estante", "sala", "depósito")
    PEOPLE = ("Ana", "Bruno", "Caio", "Dora", "Eva", "Fábio")

    @staticmethod
    def _rng(run: TestRun, cycle: int) -> random.Random:
        return random.Random((run.seed << 16) ^ (cycle * 0x9E3779B1))

    def choose_topic(self, run: TestRun, cycle: int) -> tuple[str, bool]:
        rng = self._rng(run, cycle)
        if run.last_topic is None:
            return rng.choice(TOPICS), False

        force_jump = run.topic_streak >= 2
        random_jump = rng.random() < run.jump_rate
        if force_jump or random_jump:
            candidates = [topic for topic in TOPICS if topic != run.last_topic]
            return rng.choice(candidates), True
        return run.last_topic, False

    def build(self, run: TestRun, cycle: int) -> dict[str, object]:
        rng = self._rng(run, cycle)
        topic, jumped = self.choose_topic(run, cycle)
        token = f"{run.run_id[:4]}{cycle:02d}"
        person = rng.choice(self.PEOPLE)
        obj = rng.choice(self.OBJECTS)
        color = rng.choice(self.COLORS)
        place = rng.choice(self.PLACES)

        if topic == "attribute":
            subject = f"objeto-{token}"
            assertion = f"O {subject} é {color}."
            question = f"Qual é a cor do {subject}?"
            expected = [subject, color]
        elif topic == "possession":
            subject = f"{obj}-{token}"
            assertion = f"{person} possui o {subject}."
            question = f"Quem possui o {subject}?"
            expected = [person, subject]
        elif topic == "location":
            subject = f"{obj}-{token}"
            assertion = f"O {subject} está na {place}."
            question = f"Onde está o {subject}?"
            expected = [subject, place]
        elif topic == "sequence":
            first = f"etapa-{token}-A"
            second = f"etapa-{token}-B"
            assertion = f"{first} acontece antes de {second}."
            question = f"O que acontece antes de {second}?"
            expected = [first, second]
        elif topic == "correction":
            subject = f"dispositivo-{token}"
            old_color = self.COLORS[(self.COLORS.index(color) + 1) % len(self.COLORS)]
            assertion = f"O {subject} era {old_color}, mas agora é {color}."
            question = f"Qual é a cor atual do {subject}?"
            expected = [subject, color]
        else:
            other = rng.choice([name for name in self.PEOPLE if name != person])
            assertion = f"{person} trabalha com {other} no projeto-{token}."
            question = f"Com quem {person} trabalha no projeto-{token}?"
            expected = [person, other, f"projeto-{token}"]

        return {
            "assertion": assertion,
            "question": question,
            "expected_terms": expected,
            "provider": "local-curiosity",
            "model": None,
            "topic": topic,
            "jumped": jumped,
        }


class AutonomousTestManager:
    """Owns bounded in-memory no-LLM exploration runs and streams snapshots to the UI."""

    def __init__(self, config) -> None:
        self.client = MemoriaClient(
            config.memoria_api_url,
            config.memoria_api_key,
            max(config.autotest_timeout_seconds, config.proxy_timeout_seconds),
        )
        self.curiosity = CuriosityGenerator()
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

    def _generate_scenario(self, run: TestRun, cycle: int) -> dict[str, object]:
        scenario = self.curiosity.build(run, cycle)
        topic = str(scenario["topic"])
        jumped = bool(scenario["jumped"])
        if jumped:
            run.jumps += 1
        if run.last_topic == topic:
            run.topic_streak += 1
        else:
            run.last_topic = topic
            run.topic_streak = 1
        return scenario

    def _run(self, run: TestRun) -> None:
        self._event(
            run,
            "system",
            f"Curiosidade autônoma iniciada: {run.cycles} ciclos, sem LLM.",
            kind="status",
            details={"jump_rate": run.jump_rate, "seed": run.seed},
        )
        try:
            for cycle in range(1, run.cycles + 1):
                run.pause.wait()
                if run.stop.is_set():
                    break
                scenario = self._generate_scenario(run, cycle)
                if scenario.get("jumped"):
                    self._event(
                        run,
                        "curiosity",
                        f"Salto aleatório para o domínio {scenario['topic']}.",
                        kind="jump",
                        details={"cycle": cycle, "topic": scenario["topic"]},
                    )
                self._event(
                    run,
                    "agent",
                    str(scenario["assertion"]),
                    details={
                        "cycle": cycle,
                        "provider": scenario.get("provider"),
                        "topic": scenario.get("topic"),
                    },
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
                    verdict = "✅ Intenção colapsou para a relação esperada."
                else:
                    run.failed += 1
                    verdict = "❌ A resolução não correspondeu ao gabarito."
                self._event(
                    run,
                    "evaluator",
                    verdict,
                    kind="pass" if passed else "fail",
                    details={
                        "expected_terms": scenario["expected_terms"],
                        "cycle": cycle,
                        "topic": scenario["topic"],
                    },
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

    def start(
        self,
        cycles: int,
        delay_ms: int,
        *,
        jump_rate: float = 0.35,
        seed: int | None = None,
    ) -> TestRun:
        cycles = max(1, min(int(cycles), 50))
        delay_ms = max(0, min(int(delay_ms), 10000))
        jump_rate = max(0.0, min(float(jump_rate), 1.0))
        run_id = uuid4().hex[:12]
        run = TestRun(
            run_id,
            cycles,
            delay_ms,
            f"autotest:{run_id}",
            jump_rate=jump_rate,
            seed=int(seed or 0),
        )
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
            "schema": "memoria-autotest-run/v2",
            "run_id": run.run_id,
            "status": run.status,
            "cycles": run.cycles,
            "completed_cycles": run.completed_cycles,
            "mode": "local-curiosity-no-llm",
            "curiosity": {
                "jump_rate": run.jump_rate,
                "jumps": run.jumps,
                "seed": run.seed,
                "last_topic": run.last_topic,
                "topic_streak": run.topic_streak,
            },
            "summary": {
                "passed": run.passed,
                "failed": run.failed,
                "accuracy": (run.passed / total) if total else None,
                "input_tokens": 0,
                "output_tokens": 0,
                "estimated_cost_usd": 0.0,
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
                run = self.start(
                    body.get("cycles", 5),
                    body.get("delay_ms", 500),
                    jump_rate=body.get("jump_rate", 0.35),
                    seed=body.get("seed"),
                )
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
