from app.config import Settings


def test_cors_origins_splits_and_trims_csv():
    settings = Settings(
        backend_cors_origins=" http://localhost:3000,https://example.com,  "
    )
    assert settings.cors_origins == ["http://localhost:3000", "https://example.com"]
