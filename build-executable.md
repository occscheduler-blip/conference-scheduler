# Building a Standalone Executable

This guide creates a single `.exe` (Windows) or `.app` (macOS) file that requires **nothing** to be pre-installed.

## Prerequisites for YOU (the developer)

You need these tools to **build** the executable (you only do this once):

1. **Python 3.11+** - [python.org](https://www.python.org/downloads/)
2. **Node.js** - [nodejs.org](https://nodejs.org/)

Then install PyInstaller:
```bash
pip install pyinstaller
```

## Step 1: Prepare the Frontend

The executable will serve a pre-built frontend, so build it first:

```bash
npm run build
```

This creates a `.next` directory with the compiled frontend.

## Step 2: Update Backend to Serve Frontend

The backend needs to serve the static frontend files. Modify `backend/app/main.py` to include this at the end:

```python
# Serve frontend static files
import os
from fastapi.staticfiles import StaticFiles

frontend_path = os.path.join(os.path.dirname(__file__), "../../.next/standalone")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
```

(Or I can help you with this if needed)

## Step 3: Build the Executable

### macOS (Creates .app):
```bash
pyinstaller --onefile \
  --windowed \
  --name "Conference Scheduler" \
  --icon=icon.icns \
  standalone-launcher.py
```

### Windows (Creates .exe):
```bash
pyinstaller --onefile ^
  --windowed ^
  --name "Conference Scheduler" ^
  --icon=icon.ico ^
  standalone-launcher.py
```

The executable will be in `dist/` folder.

## Step 4: Share with Her

She can:
1. Download the `.exe` or `.app` file
2. Click to run
3. Wait ~5 seconds
4. Browser opens automatically
5. Done!

---

**The executable size will be ~150-180 MB** (Python bundled in).

**Questions?** Let me know which platform (Windows, macOS, or both) you want to build for.
