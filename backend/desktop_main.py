"""Entry point for the PyInstaller-bundled FastAPI backend.

Starts uvicorn programmatically so PyInstaller can produce a single
executable. Reads PORT and HOST from env (set by the Tauri shell).
"""
import os
import sys
from pathlib import Path

# Make the bundled resource path findable for pydantic-settings.
# When running under PyInstaller, sys._MEIPASS points to the unpacked dir.
if hasattr(sys, "_MEIPASS"):
    bundle_root = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    # Tell pydantic-settings where to look for the bundled .env.
    env_file = bundle_root / ".env"
    if env_file.exists():
        os.environ.setdefault("BUNDLED_ENV_FILE", str(env_file))
        # Pre-load values from the bundled .env so any os.getenv reads pick them up.
        try:
            from dotenv import load_dotenv  # type: ignore[import-not-found]

            load_dotenv(env_file, override=False)
        except ImportError:
            # Manually parse a minimal .env if python-dotenv isn't bundled.
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                v = v.strip().strip('"').strip("'")
                os.environ.setdefault(k.strip(), v)


def main() -> None:
    import uvicorn

    host = os.environ.get("DESKTOP_HOST", "127.0.0.1")
    port = int(os.environ.get("DESKTOP_PORT", "17850"))

    # Force-allow the Tauri webview origins. The backend only listens on
    # 127.0.0.1, so it's never reachable from outside this machine.
    os.environ["BACKEND_CORS_ORIGINS"] = (
        "tauri://localhost,http://tauri.localhost,"
        "https://tauri.localhost,http://localhost"
    )

    from app.main import app  # noqa: WPS433  imported here for PyInstaller

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
