# Conference Scheduler Launcher

A simple GUI application to run the entire conference scheduler locally without needing a terminal.

## Quick Start

### Step 1: Install Prerequisites (One-time setup)

Before running the launcher, you need to install three tools:

1. **Python 3** - [Download from python.org](https://www.python.org/downloads/)
2. **Node.js** - [Download from nodejs.org](https://nodejs.org/)
3. **Docker Desktop** - [Download from docker.com](https://www.docker.com/products/docker-desktop)

> **Windows users:** Make sure to restart your computer after installing these tools so they're added to your system PATH.

### Step 2: Run the Setup Script (One-time setup)

**On macOS/Linux:**
```bash
bash setup-launcher.sh
```

**On Windows:**
```
setup-launcher.bat
```

This script will:
- ✅ Check that all dependencies are installed
- ✅ Install Python libraries for the launcher
- ✅ Install backend dependencies (FastAPI, Supabase, etc.)
- ✅ Install frontend dependencies (React, Next.js, etc.)
- ✅ Install the Supabase CLI

> **Mac users:** On your first run, you might see a "Do you want the application python to accept incoming network connections?" prompt. Click **Allow** so the backend can run.

### Step 3: Run the Launcher

**On macOS/Linux:**
```bash
python3 launcher.py
```

**On Windows:**
```
python launcher.py
```

You should see a window like this:

```
╔════════════════════════════════════════════════════════════╗
║          Conference Scheduler                              ║
║          Local Development Launcher                        ║
╠════════════════════════════════════════════════════════════╣
║ Status: Ready                                              ║
║                                                            ║
║ [Log output area - shows what's happening]                ║
║                                                            ║
║                                                            ║
║  [🟢 Start Server]  [🔴 Stop Server]  [❌ Exit]           ║
║                                                            ║
║ Frontend: http://localhost:3000                           ║
║ Backend API: http://localhost:8000/docs                   ║
╚════════════════════════════════════════════════════════════╝
```

### Step 4: Click "Start Server"

Click the **🟢 Start Server** button. The launcher will:

1. Start the database (Supabase)
2. Start the backend API (FastAPI)
3. Start the frontend server (Next.js)
4. Open your web browser to http://localhost:3000

You'll see log messages telling you what's happening. Wait about 10-15 seconds for everything to fully start.

## URLs After Starting

- **Frontend:** http://localhost:3000
- **API Documentation:** http://localhost:8000/docs (backend Swagger UI)

## Stopping the Server

Click the **🔴 Stop Server** button to shut down all services.

## Troubleshooting

### "Docker is not installed"
Docker Desktop must be installed and running. [Download it here](https://www.docker.com/products/docker-desktop) and make sure it's open.

### "Backend failed to start"
This usually means port 8000 is already in use. Close other applications that might be using port 8000 and try again.

### "Frontend won't load"
Wait a bit longer (up to 30 seconds) for the frontend to compile. You'll see build messages in the log window.

### Services start but browser won't open
Try manually visiting http://localhost:3000 in your web browser.

### Everything is stuck
Click **🔴 Stop Server**, then click **❌ Exit**. Close the launcher window and try again.

## For Developers

If you want to package this as a standalone .exe or .app:

### macOS (Creates .app)
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "Conference Scheduler" launcher.py
```

Output will be in `dist/Conference Scheduler.app`

### Windows (Creates .exe)
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "Conference Scheduler" launcher.py
```

Output will be in `dist/Conference Scheduler.exe`

---

**Questions?** Ask the developer for help with the launcher setup.
