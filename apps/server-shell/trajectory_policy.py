"""Deterministic policy that turns epistemic trajectory history into curiosity priorities."""
from __future__ import annotations


def _key(value: object) -> str:
    return str(value or "").casefold().strip()


def trajectory_signal(topic: str, snapshot: dict | None) -> dict:
    """Return a bounded priority modifier without declaring any proposition true/false."""
    key=_key(topic); snapshot=snapshot or {}; active=snapshot.get("active") or []
    matches=[x for x in active if _key(x.get("key") or x.get("topic"))==key]
    if matches:
        item=matches[-1]; gain=float(item.get("last_gain") or 0.0); steps=int(item.get("steps") or 0); generation=int(item.get("generation") or 0)
        if gain < 0:
            return {"state":"contradictory","priority":1.0,"reason":"trajectory_contradiction","generation":generation,"steps":steps}
        if gain == 0 and steps >= 2:
            return {"state":"stagnant","priority":-0.7,"reason":"trajectory_stagnation","generation":generation,"steps":steps}
        return {"state":"active","priority":0.45,"reason":"trajectory_active","generation":generation,"steps":steps}
    closed=[]
    for item in (snapshot.get("closed") or []):
        if _key(item.get("key") or item.get("topic"))==key: closed.append(item)
    if closed:
        item=closed[-1]
        return {"state":"saturated","priority":-1.0,"reason":"trajectory_saturated","generation":int(item.get("generation") or 0),"steps":int(item.get("steps") or 0)}
    return {"state":"unexplored","priority":0.7,"reason":"trajectory_unexplored","generation":0,"steps":0}


def rank_topics(candidates: list[tuple[str, float]], snapshot: dict | None, recent: list[str] | None=None) -> list[dict]:
    """Combine epistemic candidate score with trajectory history and recency pressure."""
    recent_keys={_key(x) for x in (recent or [])}
    ranked=[]
    for topic,base in candidates:
        signal=trajectory_signal(topic,snapshot); recency=-0.35 if _key(topic) in recent_keys else 0.0
        score=round(float(base)+float(signal["priority"])+recency,4)
        ranked.append({"topic":topic,"score":score,"base_score":float(base),"recency":recency,**signal})
    return sorted(ranked,key=lambda x:(-x["score"],_key(x["topic"])))
