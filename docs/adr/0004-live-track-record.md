# ADR 0004: Live track record

- Status: accepted
- Date: 2026-10-20

## Context

Backtests measure the method. Users also need to see how the predictions FightLens actually published did. That only means something if hindsight can't leak in.

## Decisions

1. **Only pre-fight predictions count.** A stored prediction is classified by when it was saved relative to the event date (UTC): `pre_fight` (an earlier day), `same_day` or `after`. Only `pre_fight` predictions enter the headline. The others are scored but reported as excluded. `same_day` is excluded on purpose, because early prelims may already have happened.
2. **One prediction per bout in the headline:** the latest pre-fight one, which is what a user last saw. Every pre-fight prediction is also scored per model version, so versions can be compared.
3. **Draws and no-contests are void.** The model is win-only, so they're counted and shown but not scored.
4. **Metrics match the backtest:** accuracy (a 50/50 call earns half credit), log loss against the coin-flip baseline, Brier score, calibration buckets, and the probability given to the exact winner and method.
5. **Scoring is a job, not a request side effect.** `fightlens score` is idempotent: one result row per prediction. `fightlens refresh` runs fetch → import → score → predict, scoring before predicting so a finished bout is judged on its pre-fight prediction. It never retrains.
6. **Finished cards show the pre-fight pick and its result**, from whichever model was active when the pick was made. A completed bout with no pre-fight prediction shows none.
7. **Small samples are labeled.** The UI warns until 50 fights are scored.
