# Model evaluation: 20261017-logistic-c59d61-r2

Generated 2026-10-21T04:24:13Z. Data through 2026-10-17 (snapshot `dd9e0c59bb92`). Feature set `fs-2` (schema `c59d61c16ff08f82`).

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
| logistic **(selected)** | 5329 | 0.6455 | 0.2270 | 62.5% |
| catboost | 5329 | 0.6500 | 0.2291 | 61.0% |
| logistic_fs1 | 5329 | 0.6583 | 0.2331 | 60.3% |

**Ablation:** the same logistic model without per-fight striking/grappling stats (`logistic_fs1`) scores 0.6583. The stats change log loss by -0.0128 (better) and accuracy by +2.1 points.

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
| 2026 | 0.6931 | 0.6858 | 0.6433 | 0.6442 | 0.6499 |

### Calibration: logistic (favourite's probability vs. how often the favourite won)

| Bucket | Bouts | Mean predicted | Observed |
|---|---:|---:|---:|
| 50%-55% | 1307 | 52.4% | 50.7% |
| 55%-60% | 1178 | 57.5% | 60.4% |
| 60%-65% | 1006 | 62.4% | 61.9% |
| 65%-70% | 761 | 67.4% | 68.2% |
| 70%-75% | 528 | 72.3% | 71.8% |
| 75%-80% | 292 | 77.2% | 77.7% |
| 80%-100% | 257 | 84.1% | 79.8% |

## Method of victory (conditional on the actual winner)

| Model | Bouts | Log loss | Accuracy | Joint 6-outcome log loss |
|---|---:|---:|---:|---:|
| prior | 5317 | 1.0242 | 49.4% | 1.6694 |
| logistic | 5317 | 0.9537 | 53.4% | 1.5989 |
| catboost **(selected)** | 5317 | 0.9477 | 53.5% | 1.5929 |

`prior` predicts training-set class frequencies. Joint log loss scores P(actual winner) × P(actual method | winner) using the best winner model.

## Logistic coefficients (standardized, before calibration)

| Feature | Coefficient |
|---|---:|
| `adj_str_off_diff` | +0.421 |
| `stats_minutes_diff` | +0.338 |
| `age_diff` | -0.333 |
| `adj_str_def_diff` | +0.330 |
| `experience_diff` | -0.258 |
| `last3_diff` | -0.178 |
| `opp_elo_last5_diff` | +0.168 |
| `str_def_diff` | +0.154 |
| `debut_diff` | -0.146 |
| `elo_diff` | +0.140 |
| `slpm_diff` | -0.128 |
| `td15_diff` | +0.121 |
| `striking_matchup` | -0.119 |
| `td_acc_diff` | -0.111 |
| `ko_loss_rate_diff` | -0.107 |
| `log_layoff_diff` | -0.103 |
| `sub_loss_rate_diff` | -0.098 |
| `wrestling_matchup` | +0.087 |
| `streak_diff` | +0.085 |
| `decision_rate_diff` | -0.083 |
| `reach_diff` | +0.077 |
| `str_acc_diff` | +0.072 |
| `win_rate_diff` | -0.067 |
| `ko_win_rate_diff` | +0.062 |
| `recent_win_rate_diff` | +0.062 |
| `sub_win_rate_diff` | +0.061 |
| `southpaw_edge` | +0.060 |
| `elo_trend_diff` | +0.050 |
| `kd_absorbed15_diff` | -0.050 |
| `td_def_diff` | +0.048 |
| `kd15_diff` | +0.048 |
| `adj_td_off_diff` | +0.043 |
| `h2h_score` | +0.037 |
| `sub15_diff` | +0.029 |
| `elo_diff_x_5rd` | -0.023 |
| `decision_rate_diff_x_5rd` | +0.021 |
| `ctrl_share_diff` | -0.020 |
| `height_diff` | +0.018 |
| `sapm_diff` | -0.006 |

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
- Six outcomes (winner × method), 4337 bouts with full method props: market log loss 1.5413, model 1.5862.

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
