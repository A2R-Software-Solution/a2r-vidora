// Pure helpers for the reel editor. They mirror the server's rules
// (functions/app/schemas/short_schema.py and pipeline/short_ass.py), so what the
// browser previews is what the renderer is asked to draw. The server still
// validates everything.

export const MAX_CAPTIONS = 60;
export const MAX_CAPTION_CHARS = 120;
export const MAX_TOTAL_CAPTION_CHARS = 4000;
export const SIZE_REFERENCE = 1080;
const EPSILON = 0.001;

// Same web fonts as the bundled render fonts, so the preview matches the video.
export const PREVIEW_FONTS = {
  poppins_semibold: { family: "Poppins", weight: 600 },
  poppins_bold: { family: "Poppins", weight: 700 },
  anton: { family: "Anton", weight: 400 },
  bebas_neue: { family: "Bebas Neue", weight: 400 },
  archivo_black: { family: "Archivo Black", weight: 400 },
  bangers: { family: "Bangers", weight: 400 },
};
export const PREVIEW_FONTS_URL = "https://fonts.googleapis.com/css2?family=Poppins:wght@600;700" +
  "&family=Anton&family=Bebas+Neue&family=Archivo+Black&family=Bangers&family=Noto+Sans+Devanagari:wght@700&display=swap";

export const DEFAULT_STYLE = Object.freeze({
  font: "poppins_semibold", size: 64, color: "#FFFFFF", outline: true, outline_color: "#000000",
  outline_width: 3, box: false, box_color: "#000000", box_opacity: 60, position: "bottom",
  uppercase: false, highlight: false, highlight_color: "#FFE600",
});

// Control characters and characters that could act as subtitle markup; the
// server removes them too.
const MARKUP = new Set(["{", "}", "\\", "<", ">"]);
const unsafe = (char) => char.charCodeAt(0) < 32 || char.charCodeAt(0) === 127 || MARKUP.has(char);
// Hindi captions: the render uses a bundled Devanagari font for these lines.
export const hasDevanagari = (text) => /[ऀ-ॿ]/.test(String(text ?? ""));

export const cleanText = (text) => Array.from(String(text ?? ""), (char) => (unsafe(char) ? " " : char))
  .join("").replace(/\s+/g, " ").trim();

const round2 = (value) => Math.round(value * 100) / 100;

export function previewScale(width, height) {
  return Math.min(width, height) / SIZE_REFERENCE;
}

export function hexToRgba(hex, opacityPercent) {
  const value = /^#[0-9a-f]{6}$/i.test(hex) ? hex : "#000000";
  const channel = (index) => parseInt(value.slice(index, index + 2), 16);
  return `rgba(${channel(1)}, ${channel(3)}, ${channel(5)}, ${Math.min(100, Math.max(0, opacityPercent)) / 100})`;
}

export function activeCaptionIndex(captions, time) {
  return captions.findIndex((caption) => time >= caption.start && time < caption.end);
}

// Words of a caption with the highlight sweeping across them: each word gets a
// share of the line proportional to its length, as in the renderer (\k tags).
export function karaokeWords(text, start, end, time) {
  const words = cleanText(text).split(" ").filter(Boolean);
  const weights = words.map((word) => word.length + 1);
  const total = weights.reduce((sum, weight) => sum + weight, 0) || 1;
  const duration = Math.max(0, end - start);
  let elapsed = 0;
  return words.map((word, index) => {
    const wordStart = start + (elapsed / total) * duration;
    elapsed += weights[index];
    return { word, lit: time >= wordStart };
  });
}

// Spreads the lines across the clip in proportion to their length, with no gaps.
export function autoSync(captions, duration) {
  const lines = captions.filter((caption) => cleanText(caption.text));
  if (!lines.length) return [];
  const weights = lines.map((caption) => cleanText(caption.text).length + 1);
  const total = weights.reduce((sum, weight) => sum + weight, 0);
  let cursor = 0;
  return lines.map((caption, index) => {
    const start = round2(cursor);
    cursor += (weights[index] / total) * duration;
    const end = index === lines.length - 1 ? round2(duration) : round2(cursor);
    return { ...caption, text: cleanText(caption.text), start, end: Math.max(end, round2(start + 0.1)) };
  });
}

// One message per problem; [] means the captions can be rendered.
export function captionErrors(captions, duration) {
  if (!captions.length) return ["Add at least one caption."];
  const errors = [];
  if (captions.length > MAX_CAPTIONS) errors.push(`Use at most ${MAX_CAPTIONS} caption lines.`);
  let total = 0;
  let previousEnd = 0;
  captions.forEach((caption, index) => {
    const label = `Line ${index + 1}`;
    const text = cleanText(caption.text);
    total += text.length;
    if (!text) errors.push(`${label} is empty.`);
    if (text.length > MAX_CAPTION_CHARS) errors.push(`${label} is longer than ${MAX_CAPTION_CHARS} characters.`);
    if (!(caption.start >= 0) || !(caption.end > caption.start)) errors.push(`${label} must end after it starts.`);
    else if (caption.end > duration + EPSILON) errors.push(`${label} ends after the clip does.`);
    if (caption.start < previousEnd - EPSILON) errors.push(`${label} overlaps the line before it.`);
    previousEnd = Math.max(previousEnd, caption.end);
  });
  if (total > MAX_TOTAL_CAPTION_CHARS) errors.push("The captions are too long in total.");
  return errors;
}

// The captions as the server expects them.
export const captionsForRequest = (captions) => captions.map((caption) => ({
  start: round2(caption.start), end: round2(caption.end), text: cleanText(caption.text),
}));

export function frameSize(ratio, options) {
  const found = options?.ratios?.find((item) => item.key === ratio);
  return found ? { width: found.width, height: found.height } : { width: 720, height: 1280 };
}

export function ratioLabel(ratio) {
  return { "9:16": "9:16 · Reels, Shorts", "1:1": "1:1 · Square", "4:5": "4:5 · Portrait", "16:9": "16:9 · Landscape" }[ratio] || ratio;
}
