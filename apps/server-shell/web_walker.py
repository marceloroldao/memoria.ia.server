"""Bounded public-web walker with canonical URLs and domain diversity."""
from __future__ import annotations
from collections import deque
from html.parser import HTMLParser
import random, time
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

DEFAULT_SEEDS=["https://pt.wikipedia.org/wiki/Especial:Aleat%C3%B3ria","https://www.nasa.gov/","https://www.mit.edu/","https://arxiv.org/","https://www.python.org/"]
TRACKING_PREFIXES=("utm_","fbclid","gclid","mc_")
SKIP_SUFFIXES=(".jpg",".jpeg",".png",".gif",".webp",".svg",".zip",".gz",".mp4",".mp3",".css",".js")

def canonical_url(url:str)->str:
    p=urlparse(url); query=[(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if not k.casefold().startswith(TRACKING_PREFIXES)]
    path=p.path or "/"; return urlunparse((p.scheme.casefold(),p.netloc.casefold(),path,"",urlencode(query),""))

def useful_url(url:str)->bool:
    p=urlparse(url); return p.scheme in {"http","https"} and bool(p.hostname) and not p.path.casefold().endswith(SKIP_SUFFIXES)

class LinkCollector(HTMLParser):
    def __init__(self,base_url:str): super().__init__(); self.base_url=base_url; self.links=[]; self._href=""; self._capture=False; self._text=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()!="a":return
        href=dict(attrs).get("href","")
        if not href or href.startswith(("#","mailto:","javascript:","tel:")):return
        url=canonical_url(urljoin(self.base_url,href))
        if not useful_url(url):return
        self._href=url; self._capture=True; self._text=[]
    def handle_data(self,data):
        if self._capture:self._text.append(data)
    def handle_endtag(self,tag):
        if tag.lower()!="a" or not self._capture:return
        title=" ".join("".join(self._text).split()) or urlparse(self._href).netloc; self.links.append((title[:200],self._href)); self._capture=False

class WebWalker:
    def __init__(self,rng:random.Random,seeds:list[str]|None=None,*,domain_cooldown_seconds:float=120.0):
        self.rng=rng; self.seeds=[canonical_url(x) for x in (seeds or DEFAULT_SEEDS)]; self.frontier=deque(maxlen=500); self.queued=set(); self.seen=set(); self.domain_last_visit={}; self.domain_visits={}; self.domain_cooldown_seconds=domain_cooldown_seconds
    def offer(self,title:str,url:str):
        url=canonical_url(url)
        if not useful_url(url) or url in self.seen or url in self.queued:return
        self.frontier.append((title[:200] or urlparse(url).netloc,url)); self.queued.add(url)
    def offer_page_links(self,page_url:str,html:str,*,max_links:int=20):
        parser=LinkCollector(page_url); parser.feed(html); candidates=[]; local=set()
        for title,url in parser.links:
            if url in local or url in self.seen or url in self.queued:continue
            local.add(url); candidates.append((title,url))
        self.rng.shuffle(candidates)
        # Interleave domains so one large site cannot monopolize the frontier.
        candidates.sort(key=lambda x:self.domain_visits.get(urlparse(x[1]).netloc.casefold(),0))
        for title,url in candidates[:max_links]:self.offer(title,url)
        return min(len(candidates),max_links)
    def _domain_ready(self,url):
        domain=urlparse(url).netloc.casefold()
        if domain not in self.domain_last_visit:return True
        return (time.monotonic()-self.domain_last_visit[domain])>=self.domain_cooldown_seconds
    def _accept(self,title,url):
        self.queued.discard(url); self.seen.add(url); domain=urlparse(url).netloc.casefold(); self.domain_last_visit[domain]=time.monotonic(); self.domain_visits[domain]=self.domain_visits.get(domain,0)+1; return title,url
    def next_candidates(self,limit:int=3):
        results=[]; attempts=0; max_attempts=len(self.frontier)+10
        while self.frontier and len(results)<limit and attempts<max_attempts:
            attempts+=1; title,url=self.frontier.popleft(); self.queued.discard(url)
            if url in self.seen:continue
            if not self._domain_ready(url):self.frontier.append((title,url)); self.queued.add(url); continue
            results.append(self._accept(title,url))
        if results:return results
        seeds=list(self.seeds); self.rng.shuffle(seeds); seeds.sort(key=lambda u:self.domain_visits.get(urlparse(u).netloc.casefold(),0))
        for url in seeds:
            if len(results)>=limit:break
            if url in self.seen or not self._domain_ready(url):continue
            results.append(self._accept(f"exploração aleatória · {urlparse(url).netloc}",url))
        return results
