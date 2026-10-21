"""`fightlens` command-line entry point for jobs that must never run inside a request."""

import argparse
import json
import sys
from pathlib import Path

from app.config import get_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fightlens")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("fetch", help="Download a new raw fightr snapshot into data/raw/")
    imp = sub.add_parser("import", help="Import a raw snapshot (default: latest) into the database")
    imp.add_argument("snapshot", nargs="?", type=Path)
    imp.add_argument("--report", type=Path, help="Write the full issue report as JSON")
    odds = sub.add_parser(
        "import-odds", help="Import bookmaker odds as a benchmark (never a feature)"
    )
    odds.add_argument(
        "csv", nargs="?", type=Path, help="Default: latest snapshot's ultimate_ufc_dataset.csv"
    )
    tr = sub.add_parser("train", help="Backtest, fit and save a versioned model bundle")
    tr.add_argument("--activate", action="store_true", help="Make the new model the active one")
    act = sub.add_parser("activate", help="Make an existing model version active")
    act.add_argument("version")
    sub.add_parser("predict", help="Store predictions for all scheduled bouts (active model)")

    args = parser.parse_args(argv)
    settings = get_settings()

    if args.command == "fetch":
        from app.ingestion.fightr import fetch_snapshot

        print(f"Saved snapshot to {fetch_snapshot(settings.data_dir)}")
        return 0

    if args.command == "import":
        from app.db.session import SessionLocal
        from app.ingestion.fightr import import_snapshot, latest_snapshot

        snapshot = args.snapshot or latest_snapshot(settings.data_dir)
        if snapshot is None:
            print("No snapshot found; run `fightlens fetch` first.", file=sys.stderr)
            return 1
        with SessionLocal() as session:
            report = import_snapshot(session, snapshot)
        print(json.dumps(report.stats(), indent=2))
        if args.report:
            args.report.write_text(json.dumps(report.issues, indent=2, default=str))
            print(f"Issue report written to {args.report}")
        return 0

    from app.db.session import SessionLocal

    if args.command == "import-odds":
        from app.benchmarks.odds import import_odds
        from app.ingestion.fightr import latest_snapshot

        path = (
            args.csv
            or (latest_snapshot(settings.data_dir) or Path(".")) / "ultimate_ufc_dataset.csv"
        )
        if not path.exists():
            print(f"{path} not found; run `fightlens fetch` first.", file=sys.stderr)
            return 1
        with SessionLocal() as session:
            report = import_odds(session, path)
        print(json.dumps(report.stats(), indent=2))
        return 0

    if args.command == "train":
        from app.ml.train import train

        with SessionLocal() as session:
            result = train(session, settings.data_dir, activate=args.activate)
        print(result.report_md)
        report_copy = Path(__file__).resolve().parents[2] / "docs" / "model-report.md"
        report_copy.write_text(result.report_md, encoding="utf-8")
        state = "active" if result.activated else "inactive (use `fightlens activate`)"
        print(f"\nSaved {result.version} to {result.artifact_dir} [{state}]")
        print(f"Report copied to {report_copy}")
        return 0

    if args.command == "activate":
        from app.ml.train import activate_version

        with SessionLocal() as session:
            activate_version(session, args.version)
        print(f"Activated {args.version}")
        return 0

    if args.command == "predict":
        from app.services.predictions import batch_predict_scheduled

        with SessionLocal() as session:
            print(json.dumps(batch_predict_scheduled(session), indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
