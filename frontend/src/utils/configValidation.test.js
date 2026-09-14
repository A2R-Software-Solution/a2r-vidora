import test from "node:test";
import assert from "node:assert/strict";
import { positiveInteger, httpUrl, requiredString } from "./configValidation.js";

test("missing config and invalid numeric values fail without fallback", () => {
  for (const value of [undefined, "", " ", "0", "-1", "1.5", "NaN"]) {
    assert.throws(() => positiveInteger(value, "TIMEOUT"));
  }
  assert.equal(positiveInteger("310000", "TIMEOUT"), 310000);
  assert.throws(() => requiredString(undefined, "SITE_KEY"), /SITE_KEY/);
});

test("URL validation rejects unsafe schemes and embedded credentials", () => {
  for (const value of ["javascript:alert(1)", "https://user:password@example.com", "invalid"]) {
    assert.throws(() => httpUrl(value, "API_URL"));
  }
  assert.equal(httpUrl("https://example.com", "API_URL"), "https://example.com");
});
