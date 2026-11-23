import assert from "node:assert/strict";
import test from "node:test";
import { clearBanNotice, isBanError, showBanNotice } from "./banNotice.js";

test("only the ban response is recognised", () => {
  const banned = { response: { status: 403, data: { code: "account_banned", reason: "Spam" } } };
  assert.equal(isBanError(banned), true);
  assert.equal(isBanError({ response: { status: 403, data: { detail: "Admin access required." } } }), false);
  assert.equal(isBanError({ response: { status: 401, data: { code: "account_banned" } } }), false);
  assert.equal(isBanError(new Error("offline")), false);
});

test("the notice can be shown and cleared without a browser", () => {
  showBanNotice("Spam");
  clearBanNotice();
  showBanNotice(undefined);
  clearBanNotice();
});
