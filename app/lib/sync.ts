/**
 * Cross-tab sync via the BroadcastChannel API.
 *
 * After a successful mutation, call `broadcastMutation({ entity, id })` to
 * signal other tabs that they should refetch. Other tabs subscribe with
 * `subscribeMutations(handler)` and call refetch as they see fit.
 *
 * Falls back to a no-op when BroadcastChannel is unavailable (older browsers,
 * SSR). Same-origin only — by design.
 */

export type MutationEvent = {
  /** Logical entity name, e.g. "symposium", "class", "professor", "presentation", "schedule". */
  entity: string;
  /** Optional id of the affected row; omit for "everything" notifications. */
  id?: string;
  /**
   * Optional client-supplied origin id; senders may set this to filter out
   * their own broadcasts on receive (some browsers deliver to self).
   */
  origin?: string;
};

const CHANNEL_NAME = "conference-scheduler-mutations";

let _channel: BroadcastChannel | null = null;

function getChannel(): BroadcastChannel | null {
  if (typeof window === "undefined") return null;
  if (typeof BroadcastChannel === "undefined") return null;
  if (_channel === null) {
    try {
      _channel = new BroadcastChannel(CHANNEL_NAME);
    } catch {
      _channel = null;
    }
  }
  return _channel;
}

export function broadcastMutation(event: MutationEvent): void {
  const channel = getChannel();
  if (!channel) return;
  try {
    channel.postMessage(event);
  } catch {
    // ignore
  }
}

export function subscribeMutations(
  handler: (event: MutationEvent) => void,
): () => void {
  const channel = getChannel();
  if (!channel) return () => {};
  const onMessage = (msg: MessageEvent<MutationEvent>) => {
    try {
      handler(msg.data);
    } catch {
      // swallow handler errors so they don't break the channel
    }
  };
  channel.addEventListener("message", onMessage);
  return () => channel.removeEventListener("message", onMessage);
}
