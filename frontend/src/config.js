// Public build-time settings only. Never put backend secrets in VITE_* variables.
const env = import.meta.env;
const positiveInteger = (name, fallback) => {
  const value = Number(env[name] ?? fallback);
  if (!Number.isSafeInteger(value) || value <= 0) {
    throw new Error(`${name} must be a positive integer`);
  }
  return value;
};

export const config = Object.freeze({
  apiBaseUrl: env.VITE_API_BASE_URL,
  isProduction: env.PROD,
  recaptchaSiteKey: env.VITE_RECAPTCHA_SITE_KEY,
  recaptchaScriptUrl: env.VITE_RECAPTCHA_SCRIPT_URL ?? "https://www.google.com/recaptcha/api.js",
  bugReportUrl: env.VITE_BUG_REPORT_URL ?? "https://forms.gle/Xw7KJ5noMo2DFTRd6",
  analysisTimeoutMs: positiveInteger("VITE_ANALYSIS_TIMEOUT_MS", 310000),
  warmupTimeoutMs: positiveInteger("VITE_WARMUP_TIMEOUT_MS", 30000),
  maxQuestions: positiveInteger("VITE_MAX_QUESTIONS", 5),
  maxQuestionChars: positiveInteger("VITE_MAX_QUESTION_CHARS", 100),
  youtubePlayerScriptUrl: env.VITE_YOUTUBE_PLAYER_SCRIPT_URL ?? "https://www.youtube.com/iframe_api",
});
