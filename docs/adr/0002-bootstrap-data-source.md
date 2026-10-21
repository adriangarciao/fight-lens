# ADR 0002: Bootstrap data source

- Status: accepted for local/MVP use; revisit before any commercial release
- Date: 2026-10-20

## Context

The handoff names UFCStats as the candidate primary source and the TidyTuesday 2026-07-07 UFC dataset as a bootstrap. Findings (details in [../data-audit.md](../data-audit.md)):

- **UFCStats** now serves a JavaScript proof-of-work "Checking your browser" challenge to non-browser clients and has no robots.txt or published terms. We read the challenge as the operator opting out of automated access, and we don't circumvent it.
- **TidyTuesday 2026-07-07** (CC0 repo) is a frozen snapshot of the `fightr` R package's data. Its completed bouts run through 2026-06-27.
- **fightr** (github.com/benyamindsmith/fightr, MIT) publishes the same tables, refreshed by GitHub Actions. On 2026-10-20 its `ufc_fights.csv` held 8,948 completed bouts (1994-03-11 → 2026-10-17) **plus scheduled bouts** for the next card.

## Decision

1. Use fightr's `data/ufc_fights.csv` as the bout/event source for completed **and** scheduled bouts. Each run saves a timestamped raw snapshot under `data/raw/fightr-YYYY-MM-DD/`.
2. Use fightr's `ufcstats_data.csv` only for **static physical attributes** (height, reach, stance, DOB). Its career-aggregate columns (SLpM, TD avg, W-L record, …) are as of the scrape date, so they leak future information into historical examples. They aren't imported into any training path.
3. TidyTuesday's `ultimate_ufc_dataset.csv` contains bookmaker odds. If used at all, it's a **benchmark only**, never a feature.
4. Don't write a UFCStats scraper.

## Known gaps

- **No per-bout striking/grappling statistics.** The bout file has outcomes, method, round/time and judging text only. Opponent-adjusted style metrics (handoff §3) can't be built until we find a legitimate per-bout stats source. The UI must label them unavailable.
- **No stable fighter IDs.** Bouts reference fighters by name. See identity rules in `backend/app/ingestion/identity.py`.
- **Rights.** fightr's code is MIT, but the underlying facts originate from UFCStats. That's fine for local/research use. Confirm redistribution rights before shipping data commercially.
