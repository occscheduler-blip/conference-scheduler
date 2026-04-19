#!/usr/bin/env python3
"""
Conference Scheduler Launcher
Simple GUI to start the app without needing a terminal.
"""

import PySimpleGUI as sg
import subprocess
import threading
import time
import webbrowser
import os
import sys
import shutil
from pathlib import Path


class AppLauncher:
    def __init__(self):
        self.processes = []
        self.running = False
        self.base_dir = Path(__file__).parent

        # Set theme
        sg.theme("DarkBlue3")

    def check_command_exists(self, cmd):
        """Check if a command exists in PATH."""
        return shutil.which(cmd) is not None

    def log_message(self, message, level="info"):
        """Return a formatted log message."""
        timestamp = time.strftime("%H:%M:%S")
        icons = {"info": "ℹ️", "error": "❌", "success": "✅", "warning": "⚠️"}
        icon = icons.get(level, "•")
        return f"{icon} [{timestamp}] {message}"

    def check_dependencies(self):
        """Check if all required tools are installed."""
        issues = []

        if not self.check_command_exists("node"):
            issues.append("Node.js is not installed")

        if not self.check_command_exists("python"):
            issues.append("Python is not installed")

        if not self.check_command_exists("docker"):
            issues.append("Docker is not installed")

        return issues

    def start_services(self, window):
        """Start all services in background thread."""
        try:
            # Update status
            window["status"].update("🚀 Starting services...\n")
            window.refresh()

            # Start Supabase
            log_text = self.log_message("Starting Supabase...", "info")
            window["log"].update(window["log"].get() + log_text + "\n")
            window.refresh()

            supabase_process = subprocess.Popen(
                ["supabase", "start"],
                cwd=str(self.base_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            self.processes.append(supabase_process)

            # Wait for Supabase to start
            time.sleep(3)

            log_text = self.log_message("Supabase started", "success")
            window["log"].update(window["log"].get() + log_text + "\n")
            window.refresh()

            # Start Backend
            log_text = self.log_message("Starting Backend (FastAPI)...", "info")
            window["log"].update(window["log"].get() + log_text + "\n")
            window.refresh()

            backend_dir = self.base_dir / "backend"
            backend_process = subprocess.Popen(
                [
                    sys.executable, "-m", "uvicorn",
                    "app.main:app", "--reload", "--port", "8000"
                ],
                cwd=str(backend_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            self.processes.append(backend_process)

            log_text = self.log_message("Backend started at http://localhost:8000", "success")
            window["log"].update(window["log"].get() + log_text + "\n")
            window.refresh()

            # Start Frontend
            log_text = self.log_message("Starting Frontend (Next.js)...", "info")
            window["log"].update(window["log"].get() + log_text + "\n")
            window.refresh()

            frontend_process = subprocess.Popen(
                ["npm", "run", "dev"],
                cwd=str(self.base_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            self.processes.append(frontend_process)

            log_text = self.log_message("Frontend starting...", "success")
            window["log"].update(window["log"].get() + log_text + "\n")

            # Wait a bit for frontend to start
            time.sleep(2)

            log_text = self.log_message("Frontend running at http://localhost:3000", "success")
            window["log"].update(window["log"].get() + log_text + "\n")
            window.refresh()

            # Update status and open browser
            window["status"].update("✅ All services running!")
            window["start_btn"].update(disabled=True)
            window["stop_btn"].update(disabled=False)

            log_text = self.log_message("Opening browser...", "info")
            window["log"].update(window["log"].get() + log_text + "\n")
            window.refresh()

            time.sleep(1)
            webbrowser.open("http://localhost:3000")

            self.running = True

        except Exception as e:
            error_msg = self.log_message(f"Error: {str(e)}", "error")
            window["log"].update(window["log"].get() + error_msg + "\n")
            window["status"].update("❌ Failed to start services")
            window.refresh()

    def stop_services(self, window):
        """Stop all running services."""
        window["status"].update("🛑 Stopping services...")
        window.refresh()

        for process in self.processes:
            try:
                process.terminate()
                process.wait(timeout=5)
            except:
                process.kill()

        self.processes = []
        self.running = False

        log_text = self.log_message("All services stopped", "info")
        window["log"].update(window["log"].get() + log_text + "\n")
        window["status"].update("⏹️ Services stopped")
        window["start_btn"].update(disabled=False)
        window["stop_btn"].update(disabled=True)
        window.refresh()

    def run(self):
        """Run the launcher GUI."""
        # Check dependencies first
        dependency_issues = self.check_dependencies()

        layout = [
            [sg.Text("Conference Scheduler", font=("Helvetica", 20, "bold"))],
            [sg.Text("Local Development Launcher", font=("Helvetica", 12, "italic"))],
            [sg.Separator()],

            # Dependency warnings
            *([[sg.Text(f"⚠️  {issue}", text_color="orange")] for issue in dependency_issues] if dependency_issues else []),
            *([[sg.Separator()] if dependency_issues else []]),

            # Status
            [sg.Text("Status:", font=("Helvetica", 10, "bold")),
             sg.Text("Ready", key="status", font=("Helvetica", 10))],

            # Log output
            [sg.Multiline(
                size=(80, 20),
                disabled=True,
                key="log",
                font=("Monaco", 9),
                background_color="#1a1a1a",
                text_color="#00ff00"
            )],

            # Buttons
            [
                sg.Button("🟢 Start Server", key="start_btn", size=(20, 2), font=("Helvetica", 12, "bold")),
                sg.Button("🔴 Stop Server", key="stop_btn", size=(20, 2), font=("Helvetica", 12, "bold"), disabled=True),
                sg.Button("❌ Exit", key="exit_btn", size=(10, 2), font=("Helvetica", 12))
            ],

            # Footer
            [sg.Text("Frontend: http://localhost:3000  |  Backend API: http://localhost:8000/docs",
                     font=("Helvetica", 9), text_color="gray")]
        ]

        window = sg.Window(
            "Conference Scheduler Launcher",
            layout,
            finalize=True,
            size=(900, 700),
            icon=None  # Can add icon path here if you have one
        )

        # Add initial log messages
        if dependency_issues:
            for issue in dependency_issues:
                log_text = self.log_message(issue, "warning")
                window["log"].update(log_text + "\n")
        else:
            log_text = self.log_message("All dependencies found!", "success")
            window["log"].update(log_text + "\n")

        while True:
            event, values = window.read(timeout=100)

            if event == sg.WINDOW_CLOSED or event == "exit_btn":
                if self.running:
                    if sg.popup_yes_no("Services are still running. Stop them and exit?") == "Yes":
                        self.stop_services(window)
                        break
                else:
                    break

            elif event == "start_btn":
                if dependency_issues:
                    sg.popup_error(
                        "Missing dependencies:\n" +
                        "\n".join(dependency_issues) +
                        "\n\nPlease install them first.",
                        title="Dependency Error"
                    )
                else:
                    thread = threading.Thread(target=self.start_services, args=(window,), daemon=True)
                    thread.start()

            elif event == "stop_btn":
                self.stop_services(window)

        # Cleanup
        if self.running:
            self.stop_services(window)

        window.close()


if __name__ == "__main__":
    launcher = AppLauncher()
    launcher.run()
