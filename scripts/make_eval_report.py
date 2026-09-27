"""Generate MODEL_EVAL_REPORT.md from ml/artifacts/backtest.json."""
import json
from pathlib import Path

base = Path(__file__).resolve().parent.parent
bt = json.loads((base / 'ml' / 'artifacts' / 'backtest.json').read_text())
meta = json.loads((base / 'ml' / 'artifacts' / 'meta.json').read_text())

def row(name, d):
    if 'linear' not in d:
        return f"| {name} | {d.get('note', 'n/a')} |"
    lines = []
    for m in ('linear', 'rf', 'gbr'):
        s = d[m]
        lines.append(f"{m}: MAE {s['mae']}, RMSE {s['rmse']}, R2 {s['r2']}, dir {s['dir_acc']} (n={s['n']})")
    return f"| {name} | " + " <br> ".join(lines) + " |"

report = f"""# Model Evaluation Report — Listing-Gain Prediction

Target: `Listing Return = (Listing Price / IPO Price) - 1` (as %).
Validation: expanding-window walk-forward sorted by `listing_date` (no shuffling).
Training set: {meta['n_train']} historical Indian IPOs (mainboard + SME flagged separately).
Model version: {meta['version']}. Features: {', '.join(meta['features'])}.

## Walk-forward results (MAE / RMSE / R2 / directional accuracy)

| Split | Linear / RF / GBR |
|---|---|
{row('all', bt.get('all', bt.get('walk_forward', {})))}
{row('mainboard', bt.get('mainboard', {}))}
{row('sme', bt.get('sme', {}))}

## Reading this honestly

- History file is a compact seed set (42 rows); treat absolute errors as
  indicative, not production guarantees. Replace/extend
  `data/historical_ipos.csv` with real NSE/BSE histories before relying on it.
- SME and mainboard are evaluated separately and must not be mixed without
  adjustment (§21 rule 3).
- Prediction intervals come from quantile regressors (q10/q90); calibration
  should be re-checked (`ml/leakage.interval_calibration`) as data grows.
- Feature contributions are descriptive of the linear model, not causal proof.
- No post-listing information enters any feature (enforced by
  `ml/features.FORBIDDEN` + `ml/leakage.assert_no_leakage` + leakage tests).
"""
(base / 'MODEL_EVAL_REPORT.md').write_text(report)
print(report)
