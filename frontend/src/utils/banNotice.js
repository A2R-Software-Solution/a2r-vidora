import { useSyncExternalStore } from "react";

// An admin can ban an account. Every request of that account then answers 403
// with code "account_banned" and the admin's message; the app shows it once.
let notice = null;
const listeners = new Set();

export const isBanError = (error) =>
  error?.response?.status === 403 && error?.response?.data?.code === "account_banned";

export function showBanNotice(reason) {
  notice = { reason: typeof reason === "string" && reason ? reason : "Please contact support." };
  listeners.forEach((listener) => listener());
}

export function clearBanNotice() {
  notice = null;
  listeners.forEach((listener) => listener());
}

const subscribe = (listener) => { listeners.add(listener); return () => listeners.delete(listener); };
export const useBanNotice = () => useSyncExternalStore(subscribe, () => notice, () => null);
