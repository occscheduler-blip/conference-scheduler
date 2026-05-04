import { useCallback, useEffect, useRef, useState } from "react";

import type { ApiResult } from "./api";

/**
 * Hook to coordinate mutating button clicks:
 *   - hard-blocks reentry while a submission is in flight (kills double-clicks)
 *   - sets up an AbortController and aborts on unmount
 *   - returns the ApiResult so callers can branch on .ok / .status
 *
 * Usage:
 *   const { isSubmitting, submit } = useSubmitGuard();
 *   const onSave = () => submit((signal) =>
 *     apiMutate("PUT", "/api/events/update_X", body, { authHeaders, signal })
 *   );
 *   <button disabled={isSubmitting} onClick={onSave}>Save</button>
 */
export function useSubmitGuard() {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const submittingRef = useRef(false);

  const submit = useCallback(
    async <T>(
      fn: (signal: AbortSignal) => Promise<ApiResult<T>>,
    ): Promise<ApiResult<T> | null> => {
      if (submittingRef.current) return null;
      submittingRef.current = true;
      setIsSubmitting(true);
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        return await fn(controller.signal);
      } finally {
        submittingRef.current = false;
        abortRef.current = null;
        setIsSubmitting(false);
      }
    },
    [],
  );

  useEffect(
    () => () => {
      abortRef.current?.abort();
    },
    [],
  );

  return { isSubmitting, submit };
}
