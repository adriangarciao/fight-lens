from app.config import get_settings
from app.db.models import ModelVersion
from app.services.predictions import bundle_dir


def test_uses_stored_path_when_it_exists(tmp_path):
    mv = ModelVersion(version="v1", artifact_path=str(tmp_path))
    assert bundle_dir(mv) == tmp_path


def test_falls_back_to_data_dir_when_stored_path_is_from_another_machine(tmp_path, monkeypatch):
    monkeypatch.setenv("FIGHTLENS_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        windows_path = r"C:\Users\someone\fight-lens\data\artifacts\v7"
        mv = ModelVersion(version="v7", artifact_path=windows_path)
        assert bundle_dir(mv) == tmp_path / "artifacts" / "v7"
    finally:
        get_settings.cache_clear()
