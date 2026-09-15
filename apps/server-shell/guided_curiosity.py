"""Trajectory-guided topic selection layered over the existing CuriosityEngine.

Kept as a subclass so concurrent changes to curiosity_engine.py remain untouched.
"""
from __future__ import annotations

from curiosity_engine import CuriosityEngine, SEEDS
from epistemic_curiosity import choose_epistemic_topic
from trajectory_policy import rank_topics


class TrajectoryGuidedCuriosityEngine(CuriosityEngine):
    def __init__(self, config, knowledge=None, trajectories=None) -> None:
        super().__init__(config, knowledge)
        self.trajectories = trajectories

    def _rank(self, candidates):
        if self.trajectories is None or not candidates:
            return []
        return rank_topics(candidates, self.trajectories.snapshot(), self.state.trajectory[-12:])

    def _guided_choice(self, candidates, source: str):
        ranked = self._rank(candidates)
        if not ranked:
            return None
        choice = ranked[0]
        self._event(
            "trajectory_guidance",
            f"Próximo endereço: {choice['topic']} ({choice['reason']}).",
            topic=choice["topic"],
            source=source,
            trajectory_state=choice["state"],
            trajectory_score=choice["score"],
            trajectory_reason=choice["reason"],
        )
        return choice

    def _choose_topic(self) -> tuple[str, str]:
        trajectory = self.state.trajectory[-12:]
        force = self.state.stagnation >= self.config.curiosity_stagnation_limit

        # First preserve the canonical epistemic-gap signal, then let trajectory
        # history decide whether that address is worth another cycle.
        if not force and self.knowledge is not None:
            selected = choose_epistemic_topic(self.knowledge, trajectory=trajectory)
            if selected is not None:
                topic, target = selected
                choice = self._guided_choice(
                    [(topic, float(target.get("epistemic_need") or 0.0))],
                    "epistemic_gap",
                )
                if choice is None or choice["state"] != "saturated":
                    self._event(
                        "epistemic_target",
                        f"Lacuna epistêmica selecionada: {topic}",
                        topic=topic,
                        **target,
                    )
                    return topic, (choice or {}).get("reason") or "epistemic_gap"
                self._event(
                    "trajectory_deferred",
                    f"Endereço saturado adiado: {topic}",
                    topic=topic,
                    trajectory_reason=choice["reason"],
                )
                force = True

        jump = force or not self.state.current_topic or self._rng.random() < self.config.curiosity_random_jump_rate
        if jump:
            candidates = [s for s in SEEDS if s not in trajectory] or list(SEEDS)
            choice = self._guided_choice([(s, 0.0) for s in candidates], "jump")
            topic = choice["topic"] if choice else self._rng.choice(candidates)
            self.state.jumps += int(bool(self.state.current_topic))
            return topic, (choice or {}).get("reason") or ("stagnation_jump" if force else "random_jump")

        recent_terms = []
        with self._lock:
            for event in list(self._events)[-20:]:
                recent_terms.extend(event.get("terms", []) or [])
        options = [t for t in dict.fromkeys(recent_terms) if t != self.state.current_topic and t not in trajectory]
        if options:
            choice = self._guided_choice([(t, 0.0) for t in options], "novel_neighbor")
            if choice:
                return choice["topic"], choice["reason"]
            return self._rng.choice(options), "novel_neighbor"
        return self.state.current_topic, "continue"

    def snapshot(self, after: int = 0):
        result = super().snapshot(after)
        result["configuration"]["trajectory_guidance"] = self.trajectories is not None
        return result
