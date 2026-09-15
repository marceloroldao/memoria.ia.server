# Epistemic gain feedback

The curiosity engine distinguishes web activity from actual knowledge improvement by comparing the selected target before and after learned evidence reaches ServerKnowledge.

For symbol `s`, unresolved need is:

`N(s)=0.45U + 0.25E + 0.20D + 0.10R`

where `U=1-confidence`, `E=1/(1+observations)`, `D=1/(1+provider_diversity)`, and `R=1/(1+relation_strength)`.

Epistemic gain is `G(s)=N_before(s)-N_after(s)`.

Interpretation: `G>0` means the addressed region became better supported; `G=0` means activity did not improve that target; `G<0` means the target became more unresolved and should remain eligible for investigation. This metric never deletes contradictory evidence: it measures support state while provenance remains preserved.

The first implementation exposes `measure_epistemic_gain()` independently so feedback semantics can be validated before asynchronous CuriosityEngine/LearningWorker synchronization is added. The next integration must correlate evidence/cycle IDs and calculate gain only after the learning worker acknowledges persistence and local knowledge update; measuring immediately after page fetch would be a race and would falsely report zero gain.
