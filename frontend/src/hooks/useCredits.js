import { useSyncExternalStore } from "react";
import { getCredits } from "../api/billingApi";

// One shared balance for the navbar, chat, Shorts and pricing page. Call
// refreshCredits() after anything that may spend or return credits.
let credits = null;
let latestRequest = 0;
const listeners = new Set();

function publish(value) {
  credits = value;
  listeners.forEach((listener) => listener());
}

export async function refreshCredits() {
  const request = ++latestRequest;
  try {
    const { data } = await getCredits();
    if (request === latestRequest) publish(data);
  } catch {
    // Unknown balance (offline, or a backend without credits): hide it.
    if (request === latestRequest) publish(null);
  }
}

function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useCredits() {
  return useSyncExternalStore(subscribe, () => credits, () => null);
}
