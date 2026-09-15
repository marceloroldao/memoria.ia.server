"""Select curiosity targets and measure knowledge gain, without LLMs."""
from __future__ import annotations


def _relation_strength(item: dict[str, object]) -> int:
    related = item.get("related") or {}
    if isinstance(related, dict):
        return sum(int(v) for v in related.values())
    return 0


def epistemic_need(item: dict[str, object]) -> float:
    """Return normalized unresolved need for one addressable content symbol."""
    confidence = float(item.get("confidence") or 0.0)
    observations = int(item.get("observations") or 0)
    providers = len(item.get("providers") or {})
    relations = _relation_strength(item)
    uncertainty = 1.0 - min(1.0, confidence)
    evidence_gap = 1.0 / (1.0 + observations)
    diversity_gap = 1.0 / (1.0 + providers)
    relation_gap = 1.0 / (1.0 + relations)
    return round(0.45 * uncertainty + 0.25 * evidence_gap + 0.20 * diversity_gap + 0.10 * relation_gap, 4)


def rank_epistemic_targets(knowledge, *, limit: int = 12) -> list[dict[str, object]]:
    recent = knowledge.recent(limit=100)
    ranked: list[dict[str, object]] = []
    for item in recent.get("items", []):
        if item.get("semantic_class") != "content":
            continue
        ranked.append({
            "topic": str(item.get("label") or item.get("key") or ""),
            "key": str(item.get("key") or ""),
            "epistemic_need": epistemic_need(item),
            "confidence": float(item.get("confidence") or 0.0),
            "observations": int(item.get("observations") or 0),
            "provider_diversity": len(item.get("providers") or {}),
            "relation_strength": _relation_strength(item),
        })
    ranked.sort(key=lambda x: (-float(x["epistemic_need"]), int(x["observations"]), str(x["topic"])))
    return ranked[:max(1, limit)]


def choose_epistemic_topic(knowledge, *, trajectory: list[str] | None = None) -> tuple[str, dict[str, object]] | None:
    trajectory_set = {str(x).casefold() for x in (trajectory or [])}
    for target in rank_epistemic_targets(knowledge):
        topic = str(target["topic"])
        if topic and topic.casefold() not in trajectory_set:
            return topic, target
    return None


def measure_epistemic_gain(knowledge, target: dict[str, object]) -> dict[str, object]:
    """Compare a selected target's current state with its pre-research state."""
    key = str(target.get("key") or "")
    before = float(target.get("epistemic_need") or 0.0)
    current = next((x for x in knowledge.recent(limit=100).get("items", []) if str(x.get("key")) == key), None)
    if current is None:
        return {"key": key, "before": before, "after": before, "gain": 0.0, "resolved": False}
    after = epistemic_need(current)
    gain = round(before - after, 4)
    return {
        "key": key, "topic": str(current.get("label") or key), "before": before, "after": after,
        "gain": gain, "resolved": gain > 0.0,
        "confidence_before": float(target.get("confidence") or 0.0),
        "confidence_after": float(current.get("confidence") or 0.0),
        "observations_before": int(target.get("observations") or 0),
        "observations_after": int(current.get("observations") or 0),
        "provider_diversity_before": int(target.get("provider_diversity") or 0),
        "provider_diversity_after": len(current.get("providers") or {}),
    }
