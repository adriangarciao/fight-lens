# Data audit: 2026-10-20

Sources checked: TidyTuesday `data/2026/2026-07-07` and fightr `data/` at commit `265a989`.

## Bout coverage (fightr `ufc_fights.csv`)

| Metric | Value |
|---|---|
| Rows | 8,962 (8,948 completed, 14 scheduled for UFC 333 on 2026-10-24) |
| Date range | 1994-03-11 → 2026-10-24 |
| Unique fighter names | ~2,700 |
| Duplicate `fight_url` | 0 |
| Same pair, same date duplicates | 1 (reported by importer) |
| Bouts per year | < 60 before 2005; ~450–520 per year since 2014 |

`f1_result` (TidyTuesday snapshot): W 5,497 · L 3,083 · NC 91 · D 65.

Methods: Decision (U/S/M) 4,076 · KO/TKO 2,753 · Submission 1,694 · TKO Doctor's Stoppage 96 · Overturned 59 · Could Not Continue 33 · DQ 23 · Other 2.

## Leakage and bias hazards

1. **Listing-order bias.** The first-listed fighter wins **64%** of decisive bouts (UFCStats lists the winner first). Fighter order must be randomized or symmetrized before training. Display code must not treat `fighter1` as "red corner".
2. **Career aggregates are current, not pre-fight.** `ufcstats_data` and `ufc_athletes` stats are as of the scrape. They're used only for physical attributes.
3. **`ultimate_ufc_dataset`.** Some "career" columns (e.g. `longest_win_streak`, `total_title_bouts`, `win_by_*`) aren't documented as strictly pre-bout. It also carries odds. Excluded from features.

## Per-fight statistics (Greco1899/scrape_ufc_stats, 2026-10-21)

42,162 per-round rows covering 8,974 bouts (1994 → 2026-10-17). Joined through the fight-details URL: 8,925 of 8,948 completed bouts matched. Issues: 116 duplicate rows from renamed events (one fight listed under two event names, kept once), 42 empty rows from early events, 6 fighter rows that couldn't be assigned to a side, 4 ambiguous bouts (the 1997 Sakuraba–Silveira double bout), 8 fights not in the bout table. Counts are written as `0.0` in most of the file; the parser accepts whole-number floats. Control time is `--` for some early bouts and treated as 0 in totals. Same rights situation as the bout data (derived from UFCStats); the repository's code is GPL-3.0.

## Bookmaker odds (benchmark only)

`ultimate_ufc_dataset.csv` (identical in TidyTuesday and fightr; 7,177 bouts, 2010-03-21 → 2026-03-28) has moneylines for 96.7% of rows and method props for about 81%. 6,702 rows matched bouts: 121 by spelling-variant or reordered-name matching, 220 unmatched (mostly name changes such as Tecia Torres → Tecia Pennington), 2 dropped for winner disagreement. The source doesn't document when lines were taken.

## Identity

The roster file has 9 names belonging to two different people (Bruno Silva, Jean Silva, Michael McDonald, Anthony Figueroa, Anthony Romero, Joey Gomez, Mike Davis, Tony Johnson, Victor Valenzuela). Bruno Silva is confirmed to have UFC bouts for both people (flyweight and middleweight). Ambiguous names are resolved by nearest listed weight to the bout's division, and every such assignment is written to the import report.

## Format differences between snapshots

| Field | TidyTuesday | fightr live |
|---|---|---|
| `date` | `2026-06-27` | `October 17, 2026` |
| `time` | `5M 0S` | `2:48` |
| roster columns | snake_case | `Name, Wins, …, STANCE, DOB` |

The importer accepts both.

## First full import (SQLite dry run, fightr snapshot 2026-10-20)

- 8,962 bouts, 2,775 fighters, 794 events imported in about 7 seconds. Re-import: 8,962 unchanged, 0 inserted/updated.
- Issues: one `duplicate_pairing`, Sakuraba vs. Silveira at UFC Ultimate Japan (1997-12-21). That's genuine: a no-contest and the tournament-final rematch on the same night. Both bouts are kept.
- No `ambiguous_identity`. Bruno Silva split 12 / 11 bouts, Jean Silva 7 / 1.
- Missing physical attributes: 104 fighters lack DOB, 660 lack reach. These stay null and are shown as unavailable.
