// Public build-time settings only. Never put backend secrets in VITE_* variables.
import { requiredString, positiveInteger, httpUrl } from "./utils/configValidation.js";
const env = import.meta.env;

export const config = Object.freeze({
  apiBaseUrl: httpUrl(env.VITE_API_BASE_URL, "VITE_API_BASE_URL"),
  isProduction: env.PROD,
  recaptchaSiteKey: requiredString(env.VITE_RECAPTCHA_SITE_KEY, "VITE_RECAPTCHA_SITE_KEY"),
  recaptchaScriptUrl: httpUrl(env.VITE_RECAPTCHA_SCRIPT_URL, "VITE_RECAPTCHA_SCRIPT_URL"),
  bugReportUrl: httpUrl(env.VITE_BUG_REPORT_URL, "VITE_BUG_REPORT_URL"),
  analysisTimeoutMs: positiveInteger(env.VITE_ANALYSIS_TIMEOUT_MS, "VITE_ANALYSIS_TIMEOUT_MS"),
  warmupTimeoutMs: positiveInteger(env.VITE_WARMUP_TIMEOUT_MS, "VITE_WARMUP_TIMEOUT_MS"),
  maxQuestions: positiveInteger(env.VITE_MAX_QUESTIONS, "VITE_MAX_QUESTIONS"),
  maxQuestionChars: positiveInteger(env.VITE_MAX_QUESTION_CHARS, "VITE_MAX_QUESTION_CHARS"),
  youtubePlayerScriptUrl: httpUrl(env.VITE_YOUTUBE_PLAYER_SCRIPT_URL, "VITE_YOUTUBE_PLAYER_SCRIPT_URL"),
});
