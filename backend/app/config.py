from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_ENV_PATH, ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_name: str = "Conference Scheduler API"
    app_env: str = "development"
    app_port: int = 8000

    backend_cors_origins: str = "http://localhost:3000"
    backend_api_key: str = ""
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_db_url: str = ""
    supabase_events_table: str = "events"
    supabase_symposiums_table: str = "symposiums"
    supabase_departments_table: str = "departments"
    supabase_timeframes_table: str = "timeframes"
    supabase_students_table: str = "students"

    jwt_secret_key: str = ""
    jwt_ttl_hours: int = 24

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.backend_cors_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
