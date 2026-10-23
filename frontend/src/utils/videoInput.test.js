import { test } from "node:test";
import assert from "node:assert/strict";
import { isYouTubeVideoUrl, friendlyApiError, YOUTUBE_LINK_MESSAGE, isYouTubeSessionUnavailable,
  CREDITS_MESSAGE, QUESTIONS_MESSAGE, analysisFailure, creditProblem } from "./videoInput.js";
import { shortError } from "./shorts.js";

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


test("credit and daily-question limits get their own messages", () => {
  const noCredits = { response: { status: 402, data: { code: "insufficient_credits", needed: 60, available: 40 } } };
  const noQuestions = { response: { status: 429, data: { code: "daily_question_limit", limit: 10 } } };
  const rateLimited = { response: { status: 429, data: { detail: "Too many requests." } } };
  assert.equal(creditProblem(noCredits), "credits");
  assert.equal(creditProblem(noQuestions), "questions");
  assert.equal(creditProblem(rateLimited), null);
  assert.equal(friendlyApiError(noCredits), CREDITS_MESSAGE);
  assert.equal(friendlyApiError(noQuestions, "qa"), QUESTIONS_MESSAGE);
  assert.match(friendlyApiError(rateLimited, "qa"), /wait a moment/);
  assert.equal(shortError(noCredits), CREDITS_MESSAGE);
});

test("failed analyses explain credits, speech and duration problems", () => {
  const credits = analysisFailure("insufficient_credits", false);
  assert.ok(credits.pricing && credits.signIn);
  assert.equal(analysisFailure("insufficient_credits", true).signIn, false);
  assert.match(analysisFailure("no_speech").text, /speech/);
  assert.ok(analysisFailure("anonymous_duration_limit").signIn);
  assert.match(analysisFailure("video_duration_limit").text, /3-hour/);
  assert.match(analysisFailure("stale_processing").text, /returned/);
});

test("only the explicit YouTube session error enables the outage UI", () => {
  const outage = { response: { status: 503, data: { detail: { code: "YOUTUBE_SESSION_UNAVAILABLE" } } } };
  assert.equal(isYouTubeSessionUnavailable(outage), true);
  assert.match(friendlyApiError(outage), /Report the issue/);
  for (const error of [{ response: { status: 429 } }, { response: { status: 503 } },
    { response: { status: 502, data: outage.response.data } }, new Error("bot")]) {
    assert.equal(isYouTubeSessionUnavailable(error), false);
  }
});
