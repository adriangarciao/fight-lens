# Model evaluation: 20261107-logistic-c59d61

Generated 2026-11-11T04:21:04Z. Data through 2026-11-07 (snapshot `b719e644e287`). Feature set `fs-2` (schema `c59d61c16ff08f82`).

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
| coin_flip | 5369 | 0.6931 | 0.2500 | 50.0% |
| elo | 5369 | 0.6815 | 0.2443 | 55.7% |
| logistic **(selected)** | 5369 | 0.6454 | 0.2270 | 62.5% |
| catboost | 5369 | 0.6496 | 0.2290 | 61.1% |
| logistic_fs1 | 5369 | 0.6581 | 0.2330 | 60.3% |

**Ablation:** the same logistic model without per-fight striking/grappling stats (`logistic_fs1`) scores 0.6581. The stats change log loss by -0.0127 (better) and accuracy by +2.2 points.

### Log loss by test year

| Year | coin_flip | elo | logistic | catboost | logistic_fs1 |
|---:|---:|---:|---:|---:|---:|
| 2016 | 0.6931 | 0.6727 | 0.6434 | 0.6433 | 0.6465 |
| 2017 | 0.6931 | 0.6820 | 0.6558 | 0.6402 | 0.6693 |
| 2018 | 0.6931 | 0.6804 | 0.6425 | 0.6564 | 0.6653 |
| 2019 | 0.6931 | 0.6972 | 0.6640 | 0.6717 | 0.6810 |
| 2020 | 0.6931 | 0.6850 | 0.6461 | 0.6501 | 0.6624 |
| 2021 | 0.6931 | 0.6828 | 0.6606 | 0.6695 | 0.6751 |
| 2022 | 0.6931 | 0.6762 | 0.6516 | 0.6579 | 0.6554 |
| 2023 | 0.6931 | 0.6820 | 0.6436 | 0.6523 | 0.6516 |
| 2024 | 0.6931 | 0.6783 | 0.6318 | 0.6429 | 0.6495 |
| 2025 | 0.6931 | 0.6765 | 0.6196 | 0.6203 | 0.6372 |
| 2026 | 0.6931 | 0.6837 | 0.6422 | 0.6411 | 0.6484 |

### Calibration: logistic (favourite's probability vs. how often the favourite won)

| Bucket | Bouts | Mean predicted | Observed |
|---|---:|---:|---:|
| 50%-55% | 1314 | 52.4% | 50.9% |
| 55%-60% | 1183 | 57.5% | 60.4% |
| 60%-65% | 1017 | 62.4% | 62.0% |
| 65%-70% | 766 | 67.4% | 68.3% |
| 70%-75% | 530 | 72.3% | 71.7% |
| 75%-80% | 299 | 77.2% | 77.3% |
| 80%-100% | 260 | 84.1% | 80.0% |

## Method of victory (conditional on the actual winner)

| Model | Bouts | Log loss | Accuracy | Joint 6-outcome log loss |
|---|---:|---:|---:|---:|
| prior | 5357 | 1.0238 | 49.4% | 1.6688 |
| logistic | 5357 | 0.9532 | 53.4% | 1.5983 |
| catboost **(selected)** | 5357 | 0.9474 | 53.6% | 1.5924 |

`prior` predicts training-set class frequencies. Joint log loss scores P(actual winner) × P(actual method | winner) using the best winner model.

## Logistic coefficients (standardized, before calibration)

| Feature | Coefficient |
|---|---:|
| `adj_str_off_diff` | +0.411 |
| `stats_minutes_diff` | +0.356 |
| `adj_str_def_diff` | +0.341 |
| `age_diff` | -0.334 |
| `experience_diff` | -0.271 |
| `last3_diff` | -0.187 |
| `opp_elo_last5_diff` | +0.160 |
| `str_def_diff` | +0.154 |
| `elo_diff` | +0.148 |
| `debut_diff` | -0.138 |
| `td15_diff` | +0.131 |
| `striking_matchup` | -0.118 |
| `slpm_diff` | -0.118 |
| `ko_loss_rate_diff` | -0.115 |
| `td_acc_diff` | -0.110 |
| `sub_loss_rate_diff` | -0.106 |
| `log_layoff_diff` | -0.100 |
| `decision_rate_diff` | -0.097 |
| `streak_diff` | +0.084 |
| `str_acc_diff` | +0.074 |
| `reach_diff` | +0.073 |
| `wrestling_matchup` | +0.073 |
| `win_rate_diff` | -0.069 |
| `recent_win_rate_diff` | +0.064 |
| `southpaw_edge` | +0.061 |
| `td_def_diff` | +0.056 |
| `sub_win_rate_diff` | +0.052 |
| `elo_trend_diff` | +0.052 |
| `ko_win_rate_diff` | +0.050 |
| `kd15_diff` | +0.048 |
| `kd_absorbed15_diff` | -0.048 |
| `adj_td_off_diff` | +0.047 |
| `h2h_score` | +0.038 |
| `ctrl_share_diff` | -0.026 |
| `sub15_diff` | +0.026 |
| `elo_diff_x_5rd` | -0.025 |
| `decision_rate_diff_x_5rd` | +0.018 |
| `height_diff` | +0.018 |
| `sapm_diff` | +0.003 |

## Benchmark: betting market (evaluation only, never a model input)

4591 backtest bouts with moneylines from the Ultimate UFC Dataset (the source doesn't document when the lines were taken). The bookmaker margin (mean overround 4.0%) is removed proportionally. Every row below is scored on exactly the same bouts.

| Predictor | Log loss | Brier | Accuracy |
|---|---:|---:|---:|
| market | 0.6065 | 0.2097 | 66.5% |
| logistic **(selected model)** | 0.6434 | 0.2262 | 62.8% |
| elo | 0.6816 | 0.2443 | 55.7% |
| catboost | 0.6488 | 0.2287 | 61.1% |
| logistic_fs1 | 0.6570 | 0.2325 | 60.5% |
| coin_flip | 0.6931 | 0.2500 | 50.0% |

- Market minus model log loss: -0.0369. The market is sharper, as expected: it prices in information the model doesn't have (injuries, weight cuts, camp news, fight footage).
- The model and the market pick the same favourite in 73.6% of bouts. Mean absolute probability gap: 11.1%.
- Six outcomes (winner × method), 4337 bouts with full method props: market log loss 1.5413, model 1.5860.

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

- Injuries, weight cuts and camp news aren't included (no historical source to validate them against).
- Per-fight stats come from UFCStats via Greco1899/scrape_ufc_stats; a few early bouts lack them and fall back to league averages.
- Common-opponent results aren't a feature: Elo already uses those same bouts, and adding both would count them twice.
- Hype and popularity are excluded from the model, as the handoff requires.
- Ages and reach come from current roster files. Static attributes are safe, but 104 fighters lack a DOB and 660 lack reach.
