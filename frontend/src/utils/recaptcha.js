import { config } from "../config";
const SITE_KEY = config.recaptchaSiteKey;
const SCRIPT_ID = "google-recaptcha-v3";

let scriptPromise;

function loadRecaptcha() {
  if (window.grecaptcha) return Promise.resolve(window.grecaptcha);
  if (scriptPromise) return scriptPromise;

  scriptPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.id = SCRIPT_ID;
    script.src = `${config.recaptchaScriptUrl}?render=${encodeURIComponent(SITE_KEY)}`;
    script.async = true;
    script.onload = () => resolve(window.grecaptcha);
    script.onerror = () => reject(new Error("Bot protection could not load. Please try again."));
    document.head.appendChild(script);
  });

  return scriptPromise;
}

export async function getRecaptchaToken(action) {
  if (!SITE_KEY) {
    if (config.isProduction) {
      throw new Error("Bot protection is not configured. Please try again later.");
    }
    return null;
  }

  const grecaptcha = await loadRecaptcha();
  return new Promise((resolve, reject) => {
    grecaptcha.ready(() => {
      grecaptcha.execute(SITE_KEY, { action }).then(resolve, reject);
    });
  });
}
