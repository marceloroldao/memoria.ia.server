"""Persistent curiosity worker with bounded web exploration and provenance."""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
import ipaddress
import json
import os
from pathlib import Path
import random
import re
import socket
from threading import Event, Lock, Thread
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen

from search_probe import SearchProbe
from search_providers import SearchProviderError, wikipedia_results

PREFIX = "/api/server/v1/curiosity"
SEEDS = [
    "robótica autônoma", "internet das coisas", "sensores", "sistemas embarcados",
    "baterias", "visão computacional", "redes distribuídas", "materiais inteligentes",
    "drones", "humanoides", "energia", "astronomia", "biologia", "economia",
]
STOP = {"para","com","uma","das","dos","que","por","the","and","from","this","that","www","http","https"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[A-Za-zÀ-ÿ0-9_-]{4,}", text.casefold()) if w not in STOP]


def _assert_external_url(url: str) -> None:
    parsed=urlparse(url)
    if parsed.scheme not in {"http","https"} or not parsed.hostname:
        raise ValueError("unsupported URL")
    host=parsed.hostname.casefold()
    if host in {"localhost","localhost.localdomain"} or host.endswith(".local"):
        raise ValueError("local URL blocked")
    try:
        infos=socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
        for info in infos:
            address=ipaddress.ip_address(info[4][0])
            if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast:
                raise ValueError("private network URL blocked")
    except socket.gaierror as exc:
        raise ValueError("hostname resolution failed") from exc


class PageHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(); self.title=""; self.description=""; self._in_title=False; self._skip=0; self._text=[]
    def handle_starttag(self, tag, attrs):
        a=dict(attrs); tag=tag.lower()
        if tag in {"script","style","noscript","svg"}: self._skip += 1
        elif tag == "title": self._in_title=True
        elif tag == "meta" and (a.get("name","").lower() == "description" or a.get("property","").lower() == "og:description"):
            self.description=a.get("content","")[:1000]
    def handle_endtag(self, tag):
        tag=tag.lower()
        if tag in {"script","style","noscript","svg"} and self._skip: self._skip -= 1
        elif tag == "title": self._in_title=False
    def handle_data(self, data):
        if self._skip: return
        text=" ".join(data.split())
        if not text: return
        if self._in_title: self.title=(self.title+" "+text).strip()
        else: self._text.append(text)
    @property
    def text(self): return " ".join(self._text)


@dataclass
class CuriosityState:
    enabled: bool = True
    status: str = "starting"
    current_topic: str = ""
    reason: str = "bootstrap"
    cycle: int = 0
    searches: int = 0
    pages_read: int = 0
    discoveries: int = 0
    jumps: int = 0
    errors: int = 0
    stagnation: int = 0
    requests_this_hour: int = 0
    hour_bucket: str = ""
    last_cycle_at: str | None = None
    last_error: str | None = None
    last_provider: str | None = None
    trajectory: list[str] = field(default_factory=list)


class CuriosityEngine:
    def __init__(self, config) -> None:
        self.config=config; self.data_dir=Path(config.curiosity_data_dir)
        self.state_file=self.data_dir/"state.json"; self.events_file=self.data_dir/"events.jsonl"
        self._lock=Lock(); self._wake=Event(); self._stop=Event(); self._events=deque(maxlen=500)
        self._seen_urls=set(); self._known_terms=set(); self._rng=random.Random(config.curiosity_seed or None)
        self.state=self._load_state(); self.state.enabled=config.curiosity_enabled
        self.data_dir.mkdir(parents=True, exist_ok=True); self._load_recent_events()
        self._thread=Thread(target=self._loop, daemon=True, name="curiosity-engine")
    def start(self): self._thread.start()
    def stop(self): self._stop.set(); self._wake.set()
    def _load_state(self) -> CuriosityState:
        try:
            raw=json.loads(self.state_file.read_text(encoding="utf-8")); return CuriosityState(**{k:v for k,v in raw.items() if k in CuriosityState.__dataclass_fields__})
        except Exception: return CuriosityState()
    def _load_recent_events(self):
        try:
            for line in self.events_file.read_text(encoding="utf-8").splitlines()[-500:]:
                event=json.loads(line); self._events.append(event)
                if event.get("url"): self._seen_urls.add(str(event["url"]))
                for term in event.get("terms",[]) or []: self._known_terms.add(str(term))
        except Exception: pass
    def _save_state(self):
        self.data_dir.mkdir(parents=True, exist_ok=True); tmp=self.state_file.with_suffix(".tmp"); tmp.write_text(json.dumps(asdict(self.state),ensure_ascii=False,indent=2),encoding="utf-8"); os.replace(tmp,self.state_file)
    def _event(self, kind: str, message: str, **details):
        event={"time":_now(),"kind":kind,"message":message,**details}
        with self._lock:
            self._events.append(event); self.data_dir.mkdir(parents=True, exist_ok=True)
            with self.events_file.open("a",encoding="utf-8") as fh: fh.write(json.dumps(event,ensure_ascii=False)+"\n")
        print(f"[curiosity] {kind}: {message}")
    def _budget(self) -> bool:
        bucket=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
        if self.state.hour_bucket != bucket: self.state.hour_bucket=bucket; self.state.requests_this_hour=0
        if self.state.requests_this_hour >= self.config.curiosity_max_requests_hour: return False
        self.state.requests_this_hour += 1; return True
    def _get(self, url: str, max_bytes: int | None=None, accept_json: bool=False) -> tuple[str,str]:
        _assert_external_url(url)
        if not self._budget(): raise RuntimeError("hourly request budget reached")
        accept = "application/json,text/plain;q=0.9,*/*;q=0.1" if accept_json else "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1"
        req=Request(url,headers={
            "User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/152.0 Safari/537.36 MemoriaIA-Curiosity/2.0",
            "Accept":accept,
            "Accept-Language":"pt-BR,pt;q=0.9,en;q=0.7",
        })
        with urlopen(req,timeout=self.config.curiosity_http_timeout) as r:
            final_url=r.geturl()
            if final_url != url: _assert_external_url(final_url)
            ctype=r.headers.get("Content-Type","")
            allowed = ("application/json" in ctype) if accept_json else ("text/html" in ctype or "text/plain" in ctype)
            if not allowed: raise ValueError(f"unsupported content type: {ctype}")
            data=r.read(max_bytes or self.config.curiosity_max_page_bytes)
            return data.decode("utf-8",errors="replace"), ctype
    def _search_duckduckgo(self, topic: str) -> list[tuple[str,str]]:
        endpoint=self.config.curiosity_search_url.replace("{query}",quote_plus(topic)).replace("QUERY",quote_plus(topic))
        html,_=self._get(endpoint,750_000)
        parser=SearchProbe(); parser.feed(html)
        dedup=[]; seen=set()
        for title,url in parser.links:
            domain=urlparse(url).netloc.casefold()
            if not domain or "duckduckgo.com" in domain or url in seen: continue
            seen.add(url); dedup.append((title,url))
        results=dedup[:self.config.curiosity_results_per_search]
        challenge=("captcha" in html.casefold() or "verify you are human" in html.casefold() or "anomaly" in html.casefold() or "duckduckgo" in html.casefold() and not results)
        if results:
            self._event("search_results",f"DuckDuckGo retornou {len(results)} resultado(s).",topic=topic,provider="duckduckgo",results=len(results))
        else:
            self._event("search_empty","DuckDuckGo retornou zero links utilizáveis.",topic=topic,provider="duckduckgo",challenge_detected=challenge,response_bytes=len(html))
        return results
    def _search(self, topic: str) -> list[tuple[str,str]]:
        self.state.searches += 1
        providers = [
            ("duckduckgo", self._search_duckduckgo),
            ("wikipedia", lambda q: wikipedia_results(q, self._get, self.config.curiosity_results_per_search)),
        ]
        for name, provider in providers:
            try:
                results = provider(topic)
            except Exception as exc:
                self._event("provider_error",str(exc),topic=topic,provider=name)
                continue
            if results:
                self.state.last_provider=name
                if name != "duckduckgo":
                    self._event("search_results",f"{name} retornou {len(results)} resultado(s).",topic=topic,provider=name,results=len(results))
                return results
            self._event("provider_fallback",f"Sem resultados em {name}; tentando próxima fonte.",topic=topic,provider=name)
        self.state.last_provider=None
        self._event("search_empty","Todos os provedores retornaram zero resultados utilizáveis.",topic=topic,provider="all")
        return []
    def _read(self, url: str) -> dict[str,object]:
        html,_=self._get(url); parser=PageHTML(); parser.feed(html); text=parser.text[:self.config.curiosity_text_limit]; counts={}
        for w in _words(parser.title+" "+parser.description+" "+text): counts[w]=counts.get(w,0)+1
        terms=[w for w,n in sorted(counts.items(),key=lambda x:(-x[1],x[0])) if n>=2][:12]; self.state.pages_read += 1
        return {"url":url,"domain":urlparse(url).netloc,"title":parser.title[:300],"description":parser.description[:1000],"excerpt":text[:1800],"terms":terms}
    def _choose_topic(self) -> tuple[str,str]:
        trajectory=self.state.trajectory[-12:]; force=self.state.stagnation >= self.config.curiosity_stagnation_limit
        jump=force or not self.state.current_topic or self._rng.random() < self.config.curiosity_random_jump_rate
        if jump:
            candidates=[s for s in SEEDS if s not in trajectory] or SEEDS; topic=self._rng.choice(candidates); self.state.jumps += int(bool(self.state.current_topic))
            return topic,"stagnation_jump" if force else "random_jump"
        recent_terms=[]
        with self._lock:
            for event in list(self._events)[-20:]: recent_terms.extend(event.get("terms",[]) or [])
        options=[t for t in dict.fromkeys(recent_terms) if t != self.state.current_topic and t not in trajectory]
        if options: return self._rng.choice(options),"novel_neighbor"
        return self.state.current_topic,"continue"
    def cycle_once(self):
        topic,reason=self._choose_topic(); self.state.current_topic=topic; self.state.reason=reason; self.state.status="searching"; self.state.cycle += 1; self.state.last_cycle_at=_now(); self.state.trajectory=(self.state.trajectory+[topic])[-50:]
        self._event("topic",f"Pesquisando: {topic}",topic=topic,reason=reason,cycle=self.state.cycle); results=self._search(topic); discoveries=0
        for title,url in results:
            if url in self._seen_urls: continue
            self._seen_urls.add(url)
            try:
                page=self._read(url); terms=list(page["terms"]); novelty=len([t for t in terms if t not in self._known_terms])/max(1,len(terms)); self._known_terms.update(terms)
                page.update({"kind":"evidence","message":str(page["title"] or title),"topic":topic,"novelty":round(novelty,3),"epistemic_status":"web_observation","confidence":0.25,"provider":self.state.last_provider}); self._event(**page); discoveries += int(novelty >= self.config.curiosity_novelty_threshold)
                if discoveries: break
            except Exception as exc: self.state.errors += 1; self._event("page_error",str(exc),url=url,topic=topic,provider=self.state.last_provider)
        if discoveries: self.state.discoveries += discoveries; self.state.stagnation=0
        else: self.state.stagnation += 1
        self.state.status="sleeping"; self.state.last_error=None; self._save_state()
    def _loop(self):
        self._event("status","Motor de curiosidade iniciado.")
        while not self._stop.is_set():
            if not self.state.enabled: self.state.status="paused"; self._save_state(); self._wake.wait(2); self._wake.clear(); continue
            try: self.cycle_once()
            except Exception as exc: self.state.errors += 1; self.state.last_error=str(exc); self.state.status="error"; self._event("error",str(exc),topic=self.state.current_topic); self._save_state()
            self._wake.wait(self.config.curiosity_interval_seconds); self._wake.clear()
        self.state.status="stopped"; self._save_state()
    def snapshot(self, after: int=0) -> dict[str,object]:
        with self._lock: events=list(self._events)
        if after>0: events=events[after:]
        return {"schema":"memoria-curiosity/v2","state":asdict(self.state),"configuration":{"interval_seconds":self.config.curiosity_interval_seconds,"max_requests_hour":self.config.curiosity_max_requests_hour,"random_jump_rate":self.config.curiosity_random_jump_rate,"stagnation_limit":self.config.curiosity_stagnation_limit,"web_enabled":True,"providers":["duckduckgo","wikipedia"]},"events":events,"event_count":len(self._events)}
    def action(self, action: str):
        if action == "pause": self.state.enabled=False; self.state.status="paused"
        elif action == "resume": self.state.enabled=True; self.state.status="running"; self._wake.set()
        elif action == "jump": self.state.stagnation=self.config.curiosity_stagnation_limit; self._wake.set(); self._event("control","Salto manual solicitado.")
        elif action == "cycle": self._wake.set(); self._event("control","Ciclo imediato solicitado.")
        else: raise ValueError("invalid curiosity action")
        self._save_state(); return self.snapshot()
    def dispatch(self, handler, path: str, query: dict[str,list[str]]) -> bool:
        if path != PREFIX and not path.startswith(PREFIX+"/"): return False
        suffix=path[len(PREFIX):].strip("/")
        try:
            if not suffix and handler.command == "GET": handler._write_json(200,self.snapshot()); return True
            if suffix in {"pause","resume","jump","cycle"} and handler.command == "POST": handler._write_json(200,self.action(suffix)); return True
        except ValueError as exc: handler._write_json(400,{"error":"invalid_curiosity_action","detail":str(exc)}); return True
        handler._write_json(405,{"error":"method_not_allowed"}); return True
