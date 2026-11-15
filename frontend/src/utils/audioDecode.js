// Browser-only audio helpers for Song Merger: an uploaded or recorded file's
// length and waveform, read on the user's device (nothing is uploaded for this).
import { peakCount, peaksFromChannels } from "./proMerge.js";

// The length the browser's own player reports, or null when it cannot tell
// (unreadable files, and recordings that carry no length).
export function readAudioDuration(file) {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const audio = new Audio();
    const finish = (value) => { URL.revokeObjectURL(url); resolve(value); };
    audio.preload = "metadata";
    audio.onloadedmetadata = () => finish(Number.isFinite(audio.duration) ? audio.duration : null);
    audio.onerror = () => finish(null);
    audio.src = url;
  });
}

// 16-bit mono WAV from samples in -1..1. Pure, so it can be tested without a browser.
export function encodeWav(samples, sampleRate) {
  const view = new DataView(new ArrayBuffer(44 + samples.length * 2));
  const text = (offset, value) => { for (let i = 0; i < value.length; i += 1) view.setUint8(offset + i, value.charCodeAt(i)); };
  text(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  text(8, "WAVEfmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);              // PCM
  view.setUint16(22, 1, true);              // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // bytes per second
  view.setUint16(32, 2, true);              // bytes per sample
  view.setUint16(34, 16, true);
  text(36, "data");
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i += 1) {
    const value = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, value < 0 ? value * 0x8000 : value * 0x7fff, true);
  }
  return view.buffer;
}

// A smaller mono copy of decoded audio that every browser can seek in.
function seekablePreview(buffer) {
  const step = buffer.sampleRate >= 44100 ? 2 : 1;
  const channels = Array.from({ length: buffer.numberOfChannels }, (_, i) => buffer.getChannelData(i));
  const samples = new Float32Array(Math.floor(buffer.length / step));
  for (let i = 0; i < samples.length; i += 1) {
    let sum = 0;
    for (const channel of channels) sum += channel[i * step];
    samples[i] = sum / channels.length;
  }
  return new Blob([encodeWav(samples, buffer.sampleRate / step)], { type: "audio/wav" });
}

// { duration, peaks, preview } for a file, or null when it is not readable audio.
// `peaks` is null when the browser can play the file but not decode it for a
// waveform; `preview` is set when the file itself cannot be seeked in (browser
// recordings), and should be played instead of the file.
export async function decodeAudioFile(file) {
  const playable = await readAudioDuration(file);
  const Context = window.AudioContext || window.webkitAudioContext;
  if (Context) {
    const context = new Context();
    try {
      const buffer = await context.decodeAudioData(await file.arrayBuffer());
      const channels = Array.from({ length: Math.min(buffer.numberOfChannels, 2) }, (_, i) => buffer.getChannelData(i));
      return {
        duration: buffer.duration,
        peaks: peaksFromChannels(channels, peakCount(buffer.duration)),
        preview: playable ? null : seekablePreview(buffer),
      };
    } catch {
      // Not decodable here; the plain player may still know its length.
    } finally {
      context.close().catch(() => {});
    }
  }
  return playable ? { duration: playable, peaks: null, preview: null } : null;
}
