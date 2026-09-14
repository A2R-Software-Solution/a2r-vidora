// Configuration validation is separate from environment-to-config mapping.
export function requiredString(value, name) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value.trim();
}

export function positiveInteger(value, name) {
  const parsed = Number(requiredString(value, name));
  if (!Number.isSafeInteger(parsed) || parsed <= 0) {
    throw new Error(`${name} must be a positive integer`);
  }
  return parsed;
}

export function httpUrl(value, name) {
  const raw = requiredString(value, name);
  let parsed;
  try { parsed = new URL(raw); } catch {
    throw new Error(`${name} must be an HTTP(S) URL`);
  }
  if (!["https:", "http:"].includes(parsed.protocol) || parsed.username || parsed.password) {
    throw new Error(`${name} must be an HTTP(S) URL without credentials`);
  }
  return raw;
}
