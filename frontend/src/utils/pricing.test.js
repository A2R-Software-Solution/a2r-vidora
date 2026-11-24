import test from "node:test";
import assert from "node:assert/strict";
import {
  FALLBACK_PACKS, FALLBACK_PACKS_INR, FALLBACK_PLANS, buyerCurrency, displayPacks, displayPlans, formatHours, formatPrice, packEquivalents,
  pricePer100Credits,
} from "./pricing.js";

test("prices are formatted from cents", () => {
  assert.equal(formatPrice(259), "$2.59");
  assert.equal(formatPrice(1000), "$10.00");
});

test("bigger packs cost less per credit", () => {
  const perCredit = FALLBACK_PACKS.map((pack) => pack.amount_cents / pack.credits);
  assert.deepEqual([...perCredit].sort((a, b) => b - a), perCredit);
  assert.deepEqual(FALLBACK_PACKS.map(pricePer100Credits), ["$2.16", "$1.67", "$1.25"]);
});

test("equivalents use 20-minute videos and 5-credit Shorts", () => {
  assert.deepEqual(packEquivalents(300), { videos: 15, videoMinutes: 20, shorts: 60 });
  assert.equal(packEquivalents(300, 10).shorts, 30);
});

test("plans from the server replace the built-in copy only when complete", () => {
  const fromServer = { ...FALLBACK_PLANS, user_monthly_credits: 30 };
  assert.equal(displayPlans(fromServer), fromServer);
  assert.equal(displayPlans(null), FALLBACK_PLANS);
  assert.equal(displayPlans({ user_monthly_credits: 30 }), FALLBACK_PLANS);
  assert.equal(displayPlans({ ...FALLBACK_PLANS, user_monthly_credits: "80" }), FALLBACK_PLANS);
});

test("retention is shown in days once it is longer than a day", () => {
  assert.deepEqual([1, 24, 36, 168].map(formatHours), ["1 hour", "24 hours", "36 hours", "7 days"]);
});

test("unknown or malformed packs fall back to the built-in list", () => {
  assert.equal(displayPacks(null), FALLBACK_PACKS);
  assert.equal(displayPacks([{ code: "mystery", credits: 1, amount_cents: 1, currency: "USD" }]), FALLBACK_PACKS);
  assert.equal(displayPacks([{ code: "pro", credits: "800", amount_cents: 1000, currency: "USD" }]), FALLBACK_PACKS);
  const fromServer = [{ code: "pro", credits: 900, amount_cents: 1000, currency: "USD" }];
  assert.deepEqual(displayPacks(fromServer), fromServer);
});

test("buyers in India see rupee packs priced in paise", () => {
  assert.equal(buyerCurrency("Asia/Kolkata"), "INR");
  assert.equal(buyerCurrency("Asia/Calcutta"), "INR");
  assert.equal(buyerCurrency("America/New_York"), "USD");
  assert.deepEqual(FALLBACK_PACKS_INR.map((pack) => formatPrice(pack.amount_cents, pack.currency)), ["₹100", "₹200", "₹500"]);
  assert.equal(formatPrice(8333, "INR"), "₹83.33");
});

test("packs in the wrong currency fall back to the buyer's built-in list", () => {
  assert.equal(displayPacks(FALLBACK_PACKS, "INR"), FALLBACK_PACKS_INR);
  assert.deepEqual(displayPacks(FALLBACK_PACKS_INR, "INR"), FALLBACK_PACKS_INR);
});

test("a coupon lowers the price like the server does, never below 1 rupee or dollar", async () => {
  const { withCoupon } = await import("./pricing.js");
  const starter = FALLBACK_PACKS_INR[1];
  const half = withCoupon(starter, { code: "HALF", percent_off: 50, bonus_credits: 0, packs: null });
  assert.equal(half.amount_cents, 10000);
  assert.equal(half.list_amount_cents, 20000);
  assert.equal(withCoupon(FALLBACK_PACKS[0], { code: "X", percent_off: 10, bonus_credits: 0, packs: null }).amount_cents, 233);
  assert.equal(withCoupon(starter, { code: "TEST", percent_off: 100, bonus_credits: 0, packs: null }).amount_cents, 100);
  const bonus = withCoupon(starter, { code: "MORE", percent_off: 0, bonus_credits: 50, packs: null });
  assert.equal(bonus.credits, 350);
  assert.equal(withCoupon(starter, { code: "PRO", percent_off: 50, bonus_credits: 0, packs: ["pro"] }), starter);
});

test("coupon errors show only the server's known reasons", async () => {
  const { couponError } = await import("./pricing.js");
  const refused = (detail, status = 400) => ({ response: { status, data: { detail } } });
  assert.equal(couponError(refused("This coupon has expired.")), "This coupon has expired.");
  assert.equal(couponError(refused("Traceback: secret")), "We couldn't check this coupon. Try again.");
  assert.equal(couponError(refused(null, 429)), "Too many tries. Wait a minute and try again.");
});
