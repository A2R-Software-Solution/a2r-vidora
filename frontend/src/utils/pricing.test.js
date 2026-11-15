import test from "node:test";
import assert from "node:assert/strict";
import {
  FALLBACK_PACKS, FALLBACK_PLANS, displayPacks, displayPlans, formatHours, formatPrice, packEquivalents,
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
  const fromServer = { ...FALLBACK_PLANS, user_daily_credits: 30 };
  assert.equal(displayPlans(fromServer), fromServer);
  assert.equal(displayPlans(null), FALLBACK_PLANS);
  assert.equal(displayPlans({ user_daily_credits: 30 }), FALLBACK_PLANS);
  assert.equal(displayPlans({ ...FALLBACK_PLANS, guest_daily_credits: "45" }), FALLBACK_PLANS);
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
