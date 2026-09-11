import { test } from "node:test";
import assert from "node:assert/strict";
import { isYouTubeVideoUrl, friendlyApiError, YOUTUBE_LINK_MESSAGE } from "./videoInput.js";

test("accepts supported YouTube video links and share parameters", () => {
  for (const url of [
    "https://www.youtube.com/watch?v=yYF2Vf1Gc14",
    "https://m.youtube.com/watch?v=yYF2Vf1Gc14&t=30",
    " https://youtu.be/yYF2Vf1Gc14?si=share ",
  ]) assert.equal(isYouTubeVideoUrl(url), true, url);
});

test("rejects text, unsupported links, malformed IDs and deceptive hosts", () => {
  for (const url of [
    "", "hello analyze this", "yYF2Vf1Gc14", "https://vimeo.com/123",
    "https://youtube.com", "https://youtube.com/playlist?list=123",
    "https://youtube.com/watch?v=abc", "https://youtu.be/yYF2Vf1Gc14/extra",
    "https://youtube.com.evil.com/watch?v=yYF2Vf1Gc14",
    "https://youtube.com@evil.com/watch?v=yYF2Vf1Gc14",
    "https://user@youtube.com/watch?v=yYF2Vf1Gc14",
    "http://youtube.com/watch?v=yYF2Vf1Gc14",
    "https://youtube.com/watch?v=yYF2Vf1Gc14 and summarize",
    "https://youtube.com/watch?v=yYF2Vf1Gc14" + "x".repeat(500),
  ]) assert.equal(isYouTubeVideoUrl(url), false, url);
});

test("all API errors produce safe text, including structured validation details", () => {
  for (const status of [400, 401, 403, 404, 409, 410, 422, 429, 500, 503, 504]) {
    for (const context of ["analyze", "restore", "qa"]) {
      const message = friendlyApiError({ response: { status, data: { detail: [{ msg: "INTERNAL_SECRET" }] } }, message: "INTERNAL_SECRET" }, context);
      assert.equal(typeof message, "string");
      assert.ok(!message.includes("INTERNAL_SECRET"));
      assert.ok(!message.includes(String(status)));
    }
  }
  assert.equal(friendlyApiError({ response: { status: 422 } }), YOUTUBE_LINK_MESSAGE);
  assert.match(friendlyApiError({ code: "ERR_NETWORK" }), /internet/);
  assert.match(friendlyApiError({ code: "ECONNABORTED" }), /longer/);
  assert.ok(!friendlyApiError(new Error("INTERNAL_SECRET")).includes("INTERNAL_SECRET"));
});
