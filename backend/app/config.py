from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FIGHTLENS_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://fightlens:fightlens@localhost:5433/fightlens"
    data_dir: Path = Path(__file__).resolve().parents[2] / "data"
    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
