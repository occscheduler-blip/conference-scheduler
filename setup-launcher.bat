@echo off
REM Conference Scheduler Launcher Setup
REM Run this once to install dependencies

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo ======================================
echo Conference Scheduler - Setup
echo ======================================
echo.

REM Check Python
echo Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ❌ Python is not installed
    echo Please install Python from https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo ✅ Python found: !PYTHON_VERSION!

REM Check Node
echo.
echo Checking Node.js...
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ❌ Node.js is not installed
    echo Please install Node.js from https://nodejs.org/
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('node --version') do set NODE_VERSION=%%i
echo ✅ Node.js found: !NODE_VERSION!

REM Check Docker
echo.
echo Checking Docker...
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ❌ Docker is not installed
    echo Please install Docker Desktop from https://www.docker.com/products/docker-desktop
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('docker --version') do set DOCKER_VERSION=%%i
echo ✅ Docker found: !DOCKER_VERSION!

REM Install launcher dependencies
echo.
echo Installing launcher dependencies...
python -m pip install -q -r launcher-requirements.txt
if %errorlevel% neq 0 (
    echo ❌ Failed to install launcher dependencies
    pause
    exit /b 1
)
echo ✅ Launcher dependencies installed

REM Install backend dependencies
echo.
echo Installing backend dependencies...
cd /d "%~dp0backend"
if not exist ".venv" (
    python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
if %errorlevel% neq 0 (
    echo ❌ Failed to install backend dependencies
    pause
    exit /b 1
)
call .venv\Scripts\deactivate.bat
echo ✅ Backend dependencies installed

REM Install frontend dependencies
echo.
echo Installing frontend dependencies...
cd /d "%~dp0"
call npm install --silent
if %errorlevel% neq 0 (
    echo ❌ Failed to install frontend dependencies
    pause
    exit /b 1
)
echo ✅ Frontend dependencies installed

REM Install Supabase CLI
echo.
echo Checking Supabase CLI...
supabase --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing Supabase CLI...
    call npm install -g @supabase/cli --silent
    echo ✅ Supabase CLI installed
) else (
    echo ✅ Supabase CLI already installed
)

echo.
echo ======================================
echo ✅ Setup complete!
echo ======================================
echo.
echo You can now run the launcher:
echo   python launcher.py
echo.
pause
