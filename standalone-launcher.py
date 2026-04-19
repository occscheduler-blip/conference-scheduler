#!/usr/bin/env python3
"""
Conference Scheduler Standalone Launcher
Starts the backend server without opening browser (to avoid tab spam).
"""

import subprocess
import time
import os
import sys
import signal
from pathlib import Path


def log(message):
    """Print a timestamped log message."""
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


backend_process = None


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    log("\n🛑 Shutting down...")
    if backend_process:
        try:
            backend_process.terminate()
            backend_process.wait(timeout=2)
        except:
            try:
                backend_process.kill()
            except:
                pass
    sys.exit(0)


def start_server():
    """Start the backend server."""
    global backend_process

    base_dir = Path(__file__).parent
    backend_dir = base_dir / "backend"

    log("=" * 70)
    log("Conference Scheduler - Server Starting")
    log("=" * 70)
    log("")

    try:
        env = os.environ.copy()
        env_file = backend_dir / ".env"

        if not env_file.exists():
            log("⚠️  Warning: No .env file found in backend/")

        # Find Python
        venv_python = backend_dir / ".venv" / "bin" / "python"
        if sys.platform == "win32":
            venv_python = backend_dir / ".venv" / "Scripts" / "python.exe"

        python_exe = str(venv_python) if venv_python.exists() else sys.executable

        log("Starting backend server...")
        log("")

        # Start the server
        backend_process = subprocess.Popen(
            [python_exe, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
            cwd=str(backend_dir),
            env=env,
        )

        time.sleep(3)

        log("✅ Server is running!")
        log("")
        log("=" * 70)
        log("OPEN YOUR BROWSER AND VISIT:")
        log("")
        log("   http://localhost:3000")
        log("")
        log("=" * 70)
        log("")
        log("API Documentation: http://localhost:8000/docs")
        log("")
        log("To stop the server: Press Ctrl+C")
        log("")

        # Set up signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Keep running
        backend_process.wait()

    except Exception as e:
        log(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    start_server()
