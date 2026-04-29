/**
 * Runtime-aware confirm/alert helpers.
 *
 * In a normal browser, `window.confirm` / `window.alert` work natively.
 * In a Tauri 2 WKWebView (macOS), those APIs return `false` immediately
 * unless we route through the Tauri dialog plugin. These helpers do the
 * detection and pick the right path.
 */

function isTauri(): boolean {
  if (typeof window === "undefined") return false;
  return (
    "__TAURI_INTERNALS__" in window ||
    "__TAURI__" in window ||
    "__TAURI_METADATA__" in window
  );
}

export async function confirmDialog(
  message: string,
  title: string = "Confirm"
): Promise<boolean> {
  if (isTauri()) {
    const { ask } = await import("@tauri-apps/plugin-dialog");
    return ask(message, { title, kind: "warning" });
  }
  return window.confirm(message);
}

export async function alertDialog(
  message: string,
  title: string = "Notice"
): Promise<void> {
  if (isTauri()) {
    const { message: showMessage } = await import("@tauri-apps/plugin-dialog");
    await showMessage(message, { title, kind: "info" });
    return;
  }
  window.alert(message);
}
