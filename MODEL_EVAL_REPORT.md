# Model Evaluation Report — Listing-Gain Prediction

Target: `Listing Return = (Listing Price / IPO Price) - 1` (as %).
Validation: expanding-window walk-forward sorted by `listing_date` (no shuffling).
Training set: 42 historical Indian IPOs (mainboard + SME flagged separately).
Model version: v1. Features: pe, ev_ebitda, rev_cagr, pat_cagr, roe, roce, debt_equity, issue_size_cr, ofs_pct, fresh_pct, val_premium, qib_x, nii_x, retail_x, total_x, anchor_pct, gmp_pct, gmp_slope, nifty_5d, vix, recent_gain, recent_sub.

## Walk-forward results (MAE / RMSE / R2 / directional accuracy)

| Split | Linear / RF / GBR |
|---|---|
| all | linear: MAE 4.318, RMSE 5.774, R2 0.887, dir 1.0 (n=27) <br> rf: MAE 4.79, RMSE 7.094, R2 0.829, dir 0.926 (n=27) <br> gbr: MAE 2.77, RMSE 3.988, R2 0.946, dir 0.926 (n=27) |
| mainboard | linear: MAE 2.219, RMSE 2.851, R2 0.958, dir 0.895 (n=19) <br> rf: MAE 2.836, RMSE 3.664, R2 0.93, dir 0.947 (n=19) <br> gbr: MAE 2.413, RMSE 3.685, R2 0.929, dir 0.947 (n=19) |
| sme | insufficient data |

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
