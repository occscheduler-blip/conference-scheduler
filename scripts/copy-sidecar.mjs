// Copy the PyInstaller-built backend executable into src-tauri/binaries/
// with the platform suffix Tauri expects for sidecars.

// PyInstaller produces an onedir bundle (folder with a binary + _internal/).
// Tauri bundles the whole folder as a "resource" so it ends up at
// Contents/Resources/conference-backend/ in the .app.
import { cpSync, rmSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(repoRoot, "backend", "dist", "conference-backend");
const dest = join(repoRoot, "src-tauri", "binaries", "conference-backend");

if (!existsSync(src)) {
  console.error(`[desktop-build] ${src} does not exist — run pyinstaller first`);
  process.exit(1);
}

if (existsSync(dest)) rmSync(dest, { recursive: true, force: true });
cpSync(src, dest, { recursive: true });

console.log(`[desktop-build] copied ${src} -> ${dest}`);
