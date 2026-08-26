"use client";

import { useEffect, useState } from "react";

import { fetchHealth } from "@/lib/api";

type Status = "checking" | "connected" | "disconnected";

const LABELS: Record<Status, string> = {
  checking: "Backend: ⏳ Checking...",
  connected: "Backend: 🟢 Connected",
  disconnected: "Backend: 🔴 Disconnected",
};

export function BackendStatus() {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    let cancelled = false;

    fetchHealth()
      .then(() => {
        if (!cancelled) setStatus("connected");
      })
      .catch(() => {
        if (!cancelled) setStatus("disconnected");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return <p>{LABELS[status]}</p>;
}
