#!/bin/bash

# Conference Scheduler Launcher Setup
# Run this once to install dependencies

set -e

echo "======================================"
echo "Conference Scheduler - Setup"
echo "======================================"
echo ""

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Check Python
echo "Checking Python..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed"
    echo "Please install Python 3 from https://www.python.org/downloads/"
    exit 1
fi
echo "✅ Python 3 found: $(python3 --version)"

# Check Node
echo ""
echo "Checking Node.js..."
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed"
    echo "Please install Node.js from https://nodejs.org/"
    exit 1
fi
echo "✅ Node.js found: $(node --version)"

# Check Docker
echo ""
echo "Checking Docker..."
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed"
    echo "Please install Docker Desktop from https://www.docker.com/products/docker-desktop"
    exit 1
fi
echo "✅ Docker found: $(docker --version)"

# Install launcher dependencies
echo ""
echo "Installing launcher dependencies..."
python3 -m pip install -q -r "$PROJECT_DIR/launcher-requirements.txt"
echo "✅ Launcher dependencies installed"

# Install backend dependencies
echo ""
echo "Installing backend dependencies..."
cd "$PROJECT_DIR/backend"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt
deactivate
echo "✅ Backend dependencies installed"

# Install frontend dependencies
echo ""
echo "Installing frontend dependencies..."
cd "$PROJECT_DIR"
npm install --silent
echo "✅ Frontend dependencies installed"

# Install Supabase CLI
echo ""
echo "Checking Supabase CLI..."
if ! command -v supabase &> /dev/null; then
    echo "Installing Supabase CLI..."
    npm install -g @supabase/cli --silent
    echo "✅ Supabase CLI installed"
else
    echo "✅ Supabase CLI already installed"
fi

echo ""
echo "======================================"
echo "✅ Setup complete!"
echo "======================================"
echo ""
echo "You can now run the launcher:"
echo "  python3 launcher.py"
echo ""
