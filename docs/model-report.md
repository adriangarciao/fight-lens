# Model evaluation: 20261017-logistic-af69f8-r3

Generated 2026-10-21T03:44:47Z. Data through 2026-10-17 (snapshot `dd9e0c59bb92`). Feature set `fs-1` (schema `af69f817125acfac`).

## Method

- Rolling backtest: for each test year Y in 2016–2026, models are fit on bouts from 2005 to Y-2, calibrated on Y-1, and scored on Y. No random splits.
- Every feature is computed from bouts strictly before the fight date (see `app/ml/features.py`).
- Models are symmetric in fighter order, so metrics don't depend on how the source lists fighters.
- Win-only model: draws and no-contests are excluded from targets (they're about 2% of bouts).
- Bookmaker odds aren't used, either as features or (yet) as a benchmark.

## Elo K selection (log loss, bouts 2005–2015)

| K | log loss |
|---:|---:|
| 16 | 0.6868 |
| 32 | 0.6827 |
| 48 | 0.6799 |
| 64 | 0.6783 |
| 96 | 0.6777 |
| 128 | 0.6799 |

Selected K = 96.

## Winner model, pooled over all test years

| Model | Bouts | Log loss | Brier | Accuracy |
|---|---:|---:|---:|---:|
| coin_flip | 5329 | 0.6931 | 0.2500 | 50.0% |
| elo | 5329 | 0.6817 | 0.2443 | 55.7% |
| logistic **(selected)** | 5329 | 0.6583 | 0.2331 | 60.3% |
| catboost | 5329 | 0.6587 | 0.2334 | 60.4% |

### Log loss by test year

| Year | coin_flip | elo | logistic | catboost |
|---:|---:|---:|---:|---:|
| 2016 | 0.6931 | 0.6727 | 0.6465 | 0.6437 |
| 2017 | 0.6931 | 0.6820 | 0.6693 | 0.6514 |
| 2018 | 0.6931 | 0.6804 | 0.6653 | 0.6776 |
| 2019 | 0.6931 | 0.6972 | 0.6810 | 0.6819 |
| 2020 | 0.6931 | 0.6850 | 0.6624 | 0.6648 |
| 2021 | 0.6931 | 0.6828 | 0.6751 | 0.6793 |
| 2022 | 0.6931 | 0.6762 | 0.6554 | 0.6578 |
| 2023 | 0.6931 | 0.6820 | 0.6516 | 0.6600 |
| 2024 | 0.6931 | 0.6783 | 0.6495 | 0.6555 |
| 2025 | 0.6931 | 0.6765 | 0.6372 | 0.6320 |
| 2026 | 0.6931 | 0.6858 | 0.6499 | 0.6409 |

### Calibration: logistic (favourite's probability vs. how often the favourite won)

| Bucket | Bouts | Mean predicted | Observed |
|---|---:|---:|---:|
| 50%-55% | 1596 | 52.5% | 50.5% |
| 55%-60% | 1348 | 57.4% | 59.9% |
| 60%-65% | 981 | 62.4% | 61.3% |
| 65%-70% | 705 | 67.4% | 67.0% |
| 70%-75% | 397 | 72.2% | 73.6% |
| 75%-80% | 197 | 77.1% | 77.2% |
| 80%-100% | 105 | 83.6% | 80.0% |

## Method of victory (conditional on the actual winner)

| Model | Bouts | Log loss | Accuracy | Joint 6-outcome log loss |
|---|---:|---:|---:|---:|
| prior | 5317 | 1.0242 | 49.4% | 1.6823 |
| logistic **(selected)** | 5317 | 0.9615 | 52.5% | 1.6196 |
| catboost | 5317 | 0.9616 | 53.2% | 1.6197 |

`prior` predicts training-set class frequencies. Joint log loss scores P(actual winner) × P(actual method | winner) using the best winner model.

## Logistic coefficients (standardized, before calibration)

| Feature | Coefficient |
|---|---:|
| `age_diff` | -0.346 |
| `debut_diff` | -0.214 |
| `last3_diff` | -0.201 |
| `recent_win_rate_diff` | +0.182 |
| `opp_elo_last5_diff` | +0.182 |
| `elo_diff` | +0.127 |
| `ko_loss_rate_diff` | -0.115 |
| `streak_diff` | +0.106 |
| `reach_diff` | +0.078 |
| `elo_trend_diff` | +0.075 |
| `log_layoff_diff` | -0.069 |
| `southpaw_edge` | +0.062 |
| `win_rate_diff` | +0.040 |
| `sub_loss_rate_diff` | -0.037 |
| `ko_win_rate_diff` | +0.030 |
| `sub_win_rate_diff` | +0.024 |
| `h2h_score` | +0.022 |
| `decision_rate_diff_x_5rd` | +0.022 |
| `experience_diff` | -0.022 |
| `elo_diff_x_5rd` | +0.011 |
| `decision_rate_diff` | +0.005 |
| `height_diff` | -0.004 |

## Benchmark: betting market (evaluation only, never a model input)

4591 backtest bouts with moneylines from the Ultimate UFC Dataset (the source doesn't document when the lines were taken). The bookmaker margin (mean overround 4.0%) is removed proportionally. Every row below is scored on exactly the same bouts.

| Predictor | Log loss | Brier | Accuracy |
|---|---:|---:|---:|
| market | 0.6065 | 0.2097 | 66.5% |
| logistic **(selected model)** | 0.6570 | 0.2325 | 60.5% |
| elo | 0.6816 | 0.2443 | 55.7% |
| catboost | 0.6581 | 0.2331 | 60.7% |
| coin_flip | 0.6931 | 0.2500 | 50.0% |

- Market minus model log loss: -0.0506. The market is sharper, as expected: it prices in information the model doesn't have (camp news, injuries, styles).
- The model and the market pick the same favourite in 71.3% of bouts. Mean absolute probability gap: 11.6%.
- Six outcomes (winner × method), 4337 bouts with full method props: market log loss 1.5413, model 1.6152.

### Market calibration (favourite's implied probability vs. how often the favourite won)

| Bucket | Bouts | Mean implied | Observed |
|---|---:|---:|---:|
| 50%-55% | 730 | 52.4% | 51.6% |
| 55%-60% | 902 | 57.6% | 57.4% |
| 60%-65% | 793 | 62.4% | 63.3% |
| 65%-70% | 761 | 67.3% | 67.4% |
| 70%-75% | 597 | 72.4% | 75.2% |
| 75%-80% | 430 | 77.4% | 83.7% |
| 80%-100% | 378 | 83.9% | 89.9% |

## Known limitations

- No per-bout striking/grappling statistics in the source, so there are no opponent-adjusted style features yet.
- Common-opponent results aren't a feature: Elo already uses those same bouts, and adding both would count them twice.
- Hype and popularity are excluded from the model, as the handoff requires.
- Ages and reach come from current roster files. Static attributes are safe, but 104 fighters lack a DOB and 660 lack reach.
