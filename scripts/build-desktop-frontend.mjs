// Build the Next.js frontend as a static export for the Tauri shell.
// The server-only `app/api/backend` route handler can't coexist with
// `output: 'export'`, so we move it aside, run next build, then restore.

import { execSync } from "node:child_process";
import { existsSync, mkdirSync, renameSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const apiDir = join(repoRoot, "app", "api");
// Move out of the `app/` tree entirely — Next still scans dot-prefixed dirs.
const apiDirHidden = join(repoRoot, ".desktop-build", "api");

const moved = existsSync(apiDir);
if (moved) {
  console.log("[desktop-build] hiding app/api so static export succeeds");
  mkdirSync(dirname(apiDirHidden), { recursive: true });
  renameSync(apiDir, apiDirHidden);
}

let exitCode = 0;
try {
  execSync("next build", {
    cwd: repoRoot,
    stdio: "inherit",
    env: {
      ...process.env,
      BUILD_TARGET: "desktop",
      NEXT_PUBLIC_BACKEND_URL: "http://127.0.0.1:17850",
    },
  });
} catch (err) {
  exitCode = err?.status ?? 1;
} finally {
  if (existsSync(apiDirHidden)) {
    console.log("[desktop-build] restoring app/api");
    renameSync(apiDirHidden, apiDir);
  }
}

process.exit(exitCode);
