// Prevents an additional console window on Windows in release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::fs::{create_dir_all, OpenOptions};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::path::BaseDirectory;
use tauri::Manager;

const BACKEND_PORT: u16 = 17850;

struct BackendState(Mutex<Option<Child>>);

#[tauri::command]
fn backend_url() -> String {
    format!("http://127.0.0.1:{BACKEND_PORT}")
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(BackendState(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![backend_url])
        .setup(|app| {
            // The PyInstaller onedir bundle lives in Resources/binaries/conference-backend/.
            // bundle.resources copies the directory tree under "binaries/" into
            // Contents/Resources/, so the binary path inside the .app is:
            //   Resources/binaries/conference-backend/conference-backend
            let resource_root = app
                .path()
                .resolve("binaries/conference-backend", BaseDirectory::Resource)?;
            let bin = resource_root.join("conference-backend");

            if !bin.exists() {
                return Err(format!(
                    "backend binary not found at {}",
                    bin.display()
                )
                .into());
            }

            // Send backend logs to ~/Library/Logs/Conference Scheduler/backend.log
            // so users can attach the file when reporting issues.
            let log_dir = app
                .path()
                .home_dir()
                .map(|h| h.join("Library/Logs/Conference Scheduler"))
                .unwrap_or_else(|_| std::env::temp_dir().join("Conference Scheduler"));
            let _ = create_dir_all(&log_dir);
            let log_path = log_dir.join("backend.log");
            let log_file = OpenOptions::new()
                .create(true)
                .append(true)
                .open(&log_path)
                .map_err(|e| format!("failed to open backend log {}: {e}", log_path.display()))?;
            let log_clone = log_file
                .try_clone()
                .map_err(|e| format!("failed to clone backend log handle: {e}"))?;

            let child = Command::new(&bin)
                .env("DESKTOP_PORT", BACKEND_PORT.to_string())
                .env("DESKTOP_HOST", "127.0.0.1")
                .env("PYTHONUNBUFFERED", "1")
                .stdout(Stdio::from(log_file))
                .stderr(Stdio::from(log_clone))
                .spawn()
                .map_err(|e| format!("failed to spawn backend at {}: {e}", bin.display()))?;

            let state: tauri::State<BackendState> = app.state();
            *state.0.lock().expect("backend state poisoned") = Some(child);

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = window.try_state::<BackendState>() {
                    if let Some(mut child) = state.0.lock().ok().and_then(|mut s| s.take()) {
                        let _ = child.kill();
                        let _ = child.wait();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
