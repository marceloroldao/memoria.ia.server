"""Select curiosity targets from weak regions of Server Knowledge, without LLMs."""
from __future__ import annotations


def _relation_strength(item: dict[str, object]) -> int:
    related = item.get("related") or {}
    if isinstance(related, dict):
        return sum(int(v) for v in related.values())
    return 0


def rank_epistemic_targets(knowledge, *, limit: int = 12) -> list[dict[str, object]]:
    """Rank addressable content symbols by epistemic need.

    Need rises with low confidence, few observations, low provider diversity and
    weak relations. Interface-noise symbols remain addressable but are not used
    to steer autonomous research.
    """
    recent = knowledge.recent(limit=100)
    ranked: list[dict[str, object]] = []
    for item in recent.get("items", []):
        if item.get("semantic_class") != "content":
            continue
        confidence = float(item.get("confidence") or 0.0)
        observations = int(item.get("observations") or 0)
        providers = len(item.get("providers") or {})
        relations = _relation_strength(item)
        uncertainty = 1.0 - min(1.0, confidence)
        evidence_gap = 1.0 / (1.0 + observations)
        diversity_gap = 1.0 / (1.0 + providers)
        relation_gap = 1.0 / (1.0 + relations)
        need = 0.45 * uncertainty + 0.25 * evidence_gap + 0.20 * diversity_gap + 0.10 * relation_gap
        ranked.append({
            "topic": str(item.get("label") or item.get("key") or ""),
            "key": str(item.get("key") or ""),
            "epistemic_need": round(need, 4),
            "confidence": confidence,
            "observations": observations,
            "provider_diversity": providers,
            "relation_strength": relations,
        })
    ranked.sort(key=lambda x: (-float(x["epistemic_need"]), int(x["observations"]), str(x["topic"])))
    return ranked[:max(1, limit)]


def choose_epistemic_topic(knowledge, *, trajectory: list[str] | None = None) -> tuple[str, dict[str, object]] | None:
    trajectory_set = {str(x).casefold() for x in (trajectory or [])}
    targets = rank_epistemic_targets(knowledge)
    for target in targets:
        topic = str(target["topic"])
        if topic and topic.casefold() not in trajectory_set:
            return topic, target
    return None
