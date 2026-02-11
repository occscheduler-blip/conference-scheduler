from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    app_name: str = "Conference Scheduler API"
    app_env: str = "development"
    app_port: int = 8000

    backend_cors_origins: str = "http://localhost:3000"

    supabase_url: str = ""
    supabase_key: str = ""
    supabase_events_table: str = "events"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
