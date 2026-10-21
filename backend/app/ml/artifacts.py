"""Versioned model bundles: serialized models + the exact feature schema they were trained on.

Loading refuses a bundle whose schema doesn't match the code's current feature definitions, so
the API can never feed a model features it wasn't trained on.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import joblib

from app.ml import features as F


class IncompatibleArtifact(RuntimeError):
    pass


@dataclass
class ModelBundle:
    version: str
    winner: object
    method: object
    metadata: dict

    @property
    def elo_k(self) -> float:
        return float(self.metadata["elo_k"])


def save_bundle(directory: Path, bundle: ModelBundle, report_md: str) -> Path:
    directory.mkdir(parents=True, exist_ok=False)
    joblib.dump(bundle.winner, directory / "winner.joblib")
    joblib.dump(bundle.method, directory / "method.joblib")
    (directory / "metadata.json").write_text(json.dumps(bundle.metadata, indent=2, default=str))
    (directory / "report.md").write_text(report_md, encoding="utf-8")
    return directory


def current_schema() -> dict:
    return {
        "feature_set_version": F.FEATURE_SET_VERSION,
        "schema_hash": F.schema_hash(),
        "winner_features": F.WINNER_FEATURES,
        "method_features": F.METHOD_FEATURES,
        "method_classes": F.METHOD_CLASSES,
    }


def load_bundle(directory: Path) -> ModelBundle:
    metadata = json.loads((directory / "metadata.json").read_text())
    check_schema(metadata)
    return ModelBundle(
        version=metadata["version"],
        winner=joblib.load(directory / "winner.joblib"),
        method=joblib.load(directory / "method.joblib"),
        metadata=metadata,
    )


def check_schema(metadata: dict) -> None:
    expected = current_schema()
    mismatched = [k for k, v in expected.items() if metadata.get(k) != v]
    if mismatched:
        raise IncompatibleArtifact(
            f"Model {metadata.get('version')!r} was trained on a different feature schema "
            f"({', '.join(mismatched)} differ). Retrain with `fightlens train`."
        )
