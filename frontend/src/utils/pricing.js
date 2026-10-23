// Credit packs and allowances. The backend is the source of truth for packs
// (GET /billing/packs); these copies render the page before that loads, at
// build-time prerender, and if the request fails. Keep them in step with
// PACKS in functions/app/services/payment_service.py.
export const FALLBACK_PACKS = [
  { code: "topup", credits: 120, amount_cents: 259, currency: "USD" },
  { code: "starter", credits: 300, amount_cents: 500, currency: "USD" },
  { code: "pro", credits: 800, amount_cents: 1000, currency: "USD" },
];

export const PACK_DETAILS = {
  topup: { name: "Top-up", blurb: "A quick refill when you need a little more." },
  starter: { name: "Starter", blurb: "For regular videos and a few Shorts." },
  pro: { name: "Pro", blurb: "Best value for heavy viewing and creating.", featured: true },
};

export const pricingMeta = {
  label: "Pricing",
  description: "Vidora AI pricing: free daily credits for every visitor, and one-time credit packs from $2.59 that never expire.",
};

export const SHORT_CREDIT_COST = 5;
const TYPICAL_VIDEO_MINUTES = 20;

export function formatPrice(amountCents, currency = "USD") {
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(amountCents / 100);
}

// Per-credit prices are fractions of a cent, so compare per 100 credits.
export function pricePer100Credits(pack) {
  return formatPrice(Math.round((pack.amount_cents * 100) / pack.credits), pack.currency);
}

// Plain-language equivalents shown under each pack.
export function packEquivalents(credits) {
  return {
    videos: Math.floor(credits / TYPICAL_VIDEO_MINUTES),
    videoMinutes: TYPICAL_VIDEO_MINUTES,
    shorts: Math.floor(credits / SHORT_CREDIT_COST),
  };
}

// Only packs with a known name, in the order the backend returned them.
export function displayPacks(packs) {
  const valid = Array.isArray(packs) ? packs.filter((pack) => PACK_DETAILS[pack?.code]
    && Number.isInteger(pack.credits) && pack.credits > 0
    && Number.isInteger(pack.amount_cents) && pack.amount_cents > 0
    && typeof pack.currency === "string") : [];
  return valid.length ? valid : FALLBACK_PACKS;
}
