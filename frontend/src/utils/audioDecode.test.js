import test from "node:test";
import assert from "node:assert/strict";
import { encodeWav } from "./audioDecode.js";

test("recordings are re-encoded as a valid 16-bit mono WAV", () => {
  const wav = new DataView(encodeWav([0, 1, -1, 0.5, 2], 24000));
  const text = (offset, length) => String.fromCharCode(...Array.from({ length }, (_, i) => wav.getUint8(offset + i)));
  assert.equal(text(0, 4) + text(8, 8) + text(36, 4), "RIFFWAVEfmt data");
  assert.equal(wav.byteLength, 44 + 10);
  assert.deepEqual([wav.getUint32(4, true), wav.getUint32(40, true)], [36 + 10, 10]);
  assert.deepEqual([wav.getUint16(22, true), wav.getUint32(24, true), wav.getUint32(28, true), wav.getUint16(34, true)], [1, 24000, 48000, 16]);
  // Samples outside -1..1 are clipped, not wrapped around.
  assert.deepEqual([0, 1, 2, 3, 4].map((i) => wav.getInt16(44 + i * 2, true)), [0, 32767, -32768, 16383, 32767]);
});
