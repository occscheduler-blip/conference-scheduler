"use client";

import { useEffect, useState } from "react";
import { toErrorMessage } from "../lib/utils";

type HealthResponse = {
  status: string;
  environment: string;
};

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

export function BackendStatus() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadHealth() {
      try {
        const response = await fetch(`${backendUrl}/health`);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const data: HealthResponse = await response.json();
        setHealth(data);
      } catch (err) {
        const message = toErrorMessage(err);
        setError(message);
      }
    }

    loadHealth();
  }, []);

  if (error) {
    return <p className="text-red-600">Backend unavailable: {error}</p>;
  }

  if (!health) {
    return <p>Checking backend connection...</p>;
  }

  return (
    <p>
      Backend status: <strong>{health.status}</strong> ({health.environment})
    </p>
  );
}
