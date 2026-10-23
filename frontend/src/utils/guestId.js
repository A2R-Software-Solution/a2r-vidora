const STORAGE_KEY = "vidora_guest_id";
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// A random id for this browser, sent as X-Guest-Id so each guest browser gets
// its own free daily credits. It identifies nothing personal. Returns null
// where storage is unavailable; the backend then falls back to the IP.
export function guestId(storage = globalThis.localStorage) {
  try {
    let id = storage.getItem(STORAGE_KEY);
    if (!UUID.test(id ?? "")) {
      id = crypto.randomUUID();
      storage.setItem(STORAGE_KEY, id);
    }
    return id;
  } catch {
    return null;
  }
}
