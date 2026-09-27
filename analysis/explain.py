"""Model explainability (§20): per-prediction feature contributions.

Uses the trained linear model's coefficients × (feature − train mean) as
approximate percentage-point contributions, plus tree-model importances as
context. Clearly labelled as descriptive, not causal.
"""
from __future__ import annotations


def explain_linear(coefs: dict[str, float], means: dict[str, float],
                   features: dict[str, float]) -> dict:
    contribs = {}
    for k, c in coefs.items():
        v = features.get(k)
        m = means.get(k, 0)
        if v is None:
            continue
        try:
            contribs[k] = round(float(c) * (float(v) - float(m)), 2)
        except Exception:
            pass
    items = sorted(contribs.items(), key=lambda x: abs(x[1]), reverse=True)
    lines = [f"{k}: {v:+.2f} pp" for k, v in items[:10]]
    return {"contributions_pp": contribs, "top_lines": lines,
            "note": "Feature contributions are descriptive of the model, "
                    "not causal proof."}
