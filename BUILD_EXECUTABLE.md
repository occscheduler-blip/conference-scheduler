# Build Standalone Executable for Distribution

This guide walks you through creating a single `.exe` (Windows) or `.app` (macOS) file that your stakeholder can run with **zero setup**.

## What She'll Get

A single file she downloads and clicks. It starts the app and opens her browser automatically. No installation, no terminal, no dependencies. Done.

---

## Prerequisites (You Only Need These to Build)

You need these tools installed **once** to create the executable:

### macOS & Linux
```bash
# Install Python if not already installed
brew install python3

# Install Node.js if not already installed  
brew install node

# Install PyInstaller
pip3 install pyinstaller
```

### Windows
1. Install Python 3.11+ from [python.org](https://www.python.org/downloads/) (check "Add Python to PATH")
2. Install Node.js from [nodejs.org](https://nodejs.org/)
3. Open Command Prompt and run:
   ```
   pip install pyinstaller
   ```

---

## Build Steps

### Step 1: Build the Frontend

From the project root:

```bash
npm install      # Install dependencies (one time)
npm run build    # Build Next.js for production
```

This creates a `.next` folder with the compiled frontend.

### Step 2: Ensure Backend Config is Ready

The backend needs a `.env` file with Supabase credentials. Check that `/backend/.env` exists and has:

```
SUPABASE_URL=https://yrwhkzrurozsfdmkazxn.supabase.co
SUPABASE_KEY=<your-key>
JWT_SECRET_KEY=<your-secret>
# ... other vars
```

If it doesn't exist, copy from `.env.example` and fill in the values.

### Step 3: Ensure Backend Dependencies are Installed

```bash
cd backend
python3 -m venv .venv          # Create virtual env (one time)
source .venv/bin/activate      # Activate it
pip install -r requirements.txt # Install dependencies
deactivate
cd ..
```

### Step 4: Create the Executable

**macOS/Linux:**
```bash
pyinstaller --onefile standalone-launcher.py
```

**Windows:**
```
pyinstaller --onefile standalone-launcher.py
```

This creates the executable in the `dist/` folder. It will take 2-5 minutes.

> **Note:** We're NOT using `--windowed` so you can see the console output and close the window easily with Ctrl+C.

### Step 5: Share the File

The executable is in one of these locations:

**macOS:** `dist/Conference Scheduler.app`
- She can drag this to her Applications folder
- Or just click it from wherever

**Windows:** `dist/Conference Scheduler.exe`
- She can click it directly
- Or create a shortcut on her desktop

---

## File Size

The executable will be **~150-180 MB** (Python is bundled inside).

---

## How She Uses It

1. Download the file
2. Double-click to run
3. Wait ~5-10 seconds while the server starts
4. Browser opens automatically to http://localhost:3000
5. When done, close the window

That's it. No terminal, no installation, nothing else needed.

---

## Troubleshooting the Build

### "ModuleNotFoundError: No module named 'uvicorn'"

The backend dependencies weren't properly installed. Run:
```bash
cd backend
source .venv/bin/activate  # macOS/Linux
# or
.venv\Scripts\activate     # Windows
pip install -r requirements.txt
```

### "PyInstaller not found"

Install it:
```bash
pip install pyinstaller
```

### "No such file or directory: '.next'"

The frontend wasn't built. Run:
```bash
npm run build
```

### The executable is huge (500MB+)

This is normal—Python itself is ~100MB. You can't make it much smaller.

### She gets "Port 8000 already in use"

Something else is using port 8000. She can:
- Close other applications
- Wait a moment and try again
- Restart her computer

---

## Advanced: Adding an Icon

To add a nice icon to the executable:

**macOS** (.icns file):
```bash
pyinstaller standalone-launcher.spec --icon=icon.icns
```

**Windows** (.ico file):
```
pyinstaller standalone-launcher.spec --icon=icon.ico
```

You can create icons using:
- [convertio.co](https://convertio.co/) (online, free)
- [ImageMagick](https://imagemagick.org/) (command-line)

---

## Questions?

If the build fails, share the error message and I can help debug.
