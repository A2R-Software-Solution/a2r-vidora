// Credit packs and allowances. The backend is the source of truth (GET
// /billing/packs and /credits/plans; an admin can change both); these copies
// render the page before that loads, at build-time prerender, and if the
// request fails. Keep them in step with the defaults in functions/app/core/config.py.
export const FALLBACK_PACKS = [
  { code: "topup", credits: 120, amount_cents: 259, currency: "USD" },
  { code: "starter", credits: 300, amount_cents: 500, currency: "USD" },
  { code: "pro", credits: 800, amount_cents: 1000, currency: "USD" },
];

// The same packs for buyers in India; amount_cents holds paise.
export const FALLBACK_PACKS_INR = [
  { code: "topup", credits: 120, amount_cents: 10000, currency: "INR" },
  { code: "starter", credits: 300, amount_cents: 20000, currency: "INR" },
  { code: "pro", credits: 800, amount_cents: 50000, currency: "INR" },
];

// INR for browsers set to Indian time, USD for everyone else. Call it only in
// the browser after the first render: the prerendered page is always in USD.
export function buyerCurrency(timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone) {
  return timeZone === "Asia/Kolkata" || timeZone === "Asia/Calcutta" ? "INR" : "USD";
}

export const fallbackPacks = (currency) => (currency === "INR" ? FALLBACK_PACKS_INR : FALLBACK_PACKS);

export const PACK_DETAILS = {
  topup: { name: "Top-up", blurb: "A quick refill when you need a little more." },
  starter: { name: "Starter", blurb: "For regular videos and a few Shorts." },
  pro: { name: "Pro", blurb: "Best value for heavy viewing and creating.", featured: true },
};

export const pricingMeta = {
  label: "Pricing",
  description: "Vidora AI pricing: free credits when you sign up, and one-time credit packs from $2.59 that never expire.",
};

export const SHORT_CREDIT_COST = 5;

export const FALLBACK_PLANS = {
  user_monthly_credits: 80, user_daily_questions: 50,
  short_credit_cost: SHORT_CREDIT_COST, free_retention_hours: 24, paid_retention_hours: 168,
};

// The backend's plans, or the built-in copy when any number is missing or malformed.
export function displayPlans(plans) {
  const valid = plans && Object.keys(FALLBACK_PLANS).every((key) => Number.isInteger(plans[key]) && plans[key] >= 0);
  return valid ? plans : FALLBACK_PLANS;
}

// "24 hours", "7 days": whole days read better once a period is longer than a day.
export function formatHours(hours) {
  if (hours > 24 && hours % 24 === 0) return `${hours / 24} days`;
  return `${hours} ${hours === 1 ? "hour" : "hours"}`;
}
const TYPICAL_VIDEO_MINUTES = 20;

// amount is in the currency's smallest unit (cents or paise). Whole rupees show
// without decimals: ₹100, not ₹100.00.
export function formatPrice(amountCents, currency = "USD") {
  const whole = currency === "INR" && amountCents % 100 === 0;
  return new Intl.NumberFormat(currency === "INR" ? "en-IN" : "en-US",
    { style: "currency", currency, ...(whole && { maximumFractionDigits: 0 }) }).format(amountCents / 100);
}

// Per-credit prices are fractions of a cent, so compare per 100 credits.
export function pricePer100Credits(pack) {
  return formatPrice(Math.round((pack.amount_cents * 100) / pack.credits), pack.currency);
}

// Plain-language equivalents shown under each pack.
export function packEquivalents(credits, shortCost = SHORT_CREDIT_COST) {
  return {
    videos: Math.floor(credits / TYPICAL_VIDEO_MINUTES),
    videoMinutes: TYPICAL_VIDEO_MINUTES,
    shorts: Math.floor(credits / shortCost),
  };
}

// Only packs with a known name, in the order the backend returned them.
export function displayPacks(packs, currency = "USD") {
  const valid = Array.isArray(packs) ? packs.filter((pack) => PACK_DETAILS[pack?.code]
    && Number.isInteger(pack.credits) && pack.credits > 0
    && Number.isInteger(pack.amount_cents) && pack.amount_cents > 0
    && pack.currency === currency) : [];
  return valid.length ? valid : fallbackPacks(currency);
}
