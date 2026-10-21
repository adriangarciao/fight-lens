# ADR 0003: Baseline model design

- Status: accepted
- Date: 2026-10-20

## Decisions

1. **One feature engine for training and inference.** `HistoryEngine` replays completed bouts by date. All bouts on a date are featurized before any result from that date is applied, which also covers one-night tournaments. Inference replays history up to the as-of date and calls the same snapshot and feature functions.

2. **Symmetry by construction, not by shuffling.** Winner features are A−B differences, so they're antisymmetric. Logistic regression has no intercept and scales without centering. CatBoost is trained on both orientations, and its predictions are averaged over both. Calibration is a slope-only Platt fit, `sigmoid(a·logit p)`. So P(A)+P(B)=1 exactly, and source listing order (which correlates with the winner) can't leak.

3. **Win-only target, conditional method model.** Draws and no-contests (~2%) are excluded from targets. P(method | winner) comes from a separate multinomial model over KO/TKO, SUB and DEC. Doctor stoppages count as KO/TKO; DQ, overturned and could-not-continue are excluded. The six joint outcomes are P(win) × P(method | win) and sum to 1. A direct six-class model is deferred until it's shown to be better calibrated.

4. **Time-respecting evaluation.** Each test year Y trains on 2005…Y−2, calibrates on Y−1, and is scored on Y, for 2016 onward. Elo's K is tuned only on 2005–2015. The production bundle trains on everything up to the last 365 days and calibrates on those 365 days.

5. **Model selection by pooled backtest log loss**, among Elo, logistic and CatBoost. The first run picked logistic: 0.6583, against 0.6587 for CatBoost, 0.6817 for Elo and 0.6931 for 50/50. See `docs/model-report.md`.

6. **Explanations are the active model's own attributions**: exact coefficient × value for logistic, symmetrized SHAP for CatBoost. They're **grouped** where features are collinear (rating, form, durability…). Individually, collinear coefficients can point the wrong way (`last3_diff` has a negative weight while recency-weighted form is positive), and listing them separately would be misleading. Each reason shows the actual input values.

7. **Artifacts are refused on schema mismatch.** A bundle stores the feature-set version, feature lists and a schema hash. Loading compares them with the code and raises `IncompatibleArtifact`, which the API returns as 503 rather than predicting.

8. **Predictions on completed bouts are flagged `in_sample`** when the production model's training window covers them. They're hindsight, not forecasts.

9. **Scheduled rounds for upcoming bouts** are filled from UFC rules (title fight or main event → 5, else 3) only when the source omits them. The source of each value is stored (`scheduled_rounds_source`) and shown.

## Deliberately excluded

- Common-opponent features: Elo already uses those same bouts, so adding both would count them twice.
- Hype and popularity (handoff §3), and bookmaker odds as features.
- Per-bout striking/grappling statistics: there's no permitted source yet.
