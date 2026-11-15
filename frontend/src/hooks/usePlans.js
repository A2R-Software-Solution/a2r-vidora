import { useSyncExternalStore } from "react";
import { getPlans } from "../api/billingApi";
import { FALLBACK_PLANS, displayPlans } from "../utils/pricing";

// Daily allowances and prices shown in the app's copy. An admin can change them,
// so they are loaded once from the backend; the built-in copy is shown until then.
let plans = FALLBACK_PLANS;
let requested = false;
const listeners = new Set();

export function loadPlans() {
  if (requested) return;
  requested = true;
  getPlans().then(({ data }) => {
    plans = displayPlans(data);
    listeners.forEach((listener) => listener());
  }).catch(() => { requested = false; });
}

function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function usePlans() {
  return useSyncExternalStore(subscribe, () => plans, () => FALLBACK_PLANS);
}
