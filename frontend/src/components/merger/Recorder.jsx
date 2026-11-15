import { useEffect, useRef, useState } from "react";
import { formatTime } from "../../utils/formatTime";
import { megabytes } from "../../utils/audioMerge";
import { recordingExtension } from "../../utils/proMerge";

const MIME_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
const SAMPLE_EVERY_MS = 60;
const BAR = 3;
const GAP = 3;

function drawLevels(canvas, levels) {
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  if (canvas.width !== Math.round(width * ratio)) {
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
  }
  const context = canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, width, height);
  // The newest level sits at the marker on the right; older ones scroll left.
  const marker = width - 24;
  context.fillStyle = "#f2652a";
  for (let i = 0; i < levels.length; i += 1) {
    const x = marker - (levels.length - i) * (BAR + GAP);
    if (x < 0) continue;
    const barHeight = Math.max(levels[i] * (height - 24), 3);
    context.beginPath();
    context.roundRect(x, (height - barHeight) / 2, BAR, barHeight, 1.5);
    context.fill();
  }
  context.fillStyle = "#e2501a";
  context.fillRect(marker, 6, 2, height - 12);
  context.beginPath();
  context.arc(marker + 1, 6, 4, 0, Math.PI * 2);
  context.fill();
}

// Records the microphone into a file that becomes a song in the editor.
export default function Recorder({ limits, onDone, onClose }) {
  const [phase, setPhase] = useState("idle");   // idle | recording
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState("");
  const canvasRef = useRef(null);
  const session = useRef(null);
  const maxSeconds = limits.max_segment_seconds;

  const finish = (save) => {
    const current = session.current;
    if (!current || current.done) return;
    current.done = true;
    current.save = save;
    cancelAnimationFrame(current.frame);
    if (current.recorder.state !== "inactive") current.recorder.stop();
    current.stream.getTracks().forEach((track) => track.stop());
    current.context.close().catch(() => {});
  };

  // Leaving the editor (or closing this card) releases the microphone.
  useEffect(() => () => finish(false), []);

  const start = async () => {
    setError("");
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError("Recording isn't supported in this browser. Upload an audio file instead.");
      return;
    }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError("We need your microphone to record. Allow it in your browser and try again.");
      return;
    }
    const mimeType = MIME_TYPES.find((type) => MediaRecorder.isTypeSupported(type));
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    const context = new (window.AudioContext || window.webkitAudioContext)();
    const analyser = context.createAnalyser();
    analyser.fftSize = 1024;
    context.createMediaStreamSource(stream).connect(analyser);
    const current = { recorder, stream, context, chunks: [], bytes: 0, levels: [], frame: 0, done: false, save: false };
    session.current = current;

    recorder.ondataavailable = (event) => {
      if (!event.data.size) return;
      current.chunks.push(event.data);
      current.bytes += event.data.size;
      // Stop while the file still fits the upload limit.
      if (current.bytes > limits.max_upload_bytes * 0.95) finish(true);
    };
    recorder.onstop = () => {
      setPhase("idle");
      setSeconds(0);
      if (!current.save || !current.chunks.length) return;
      const type = recorder.mimeType || mimeType || "audio/webm";
      onDone(new File(current.chunks, `recording${recordingExtension(type)}`, { type }));
    };

    const samples = new Uint8Array(analyser.fftSize);
    const startedAt = performance.now();
    let lastSample = 0;
    const tick = (now) => {
      if (current.done) return;
      if (now - lastSample >= SAMPLE_EVERY_MS) {
        lastSample = now;
        analyser.getByteTimeDomainData(samples);
        let peak = 0;
        for (const value of samples) peak = Math.max(peak, Math.abs(value - 128) / 128);
        current.levels.push(peak);
        if (current.levels.length > 600) current.levels.shift();
        if (canvasRef.current) drawLevels(canvasRef.current, current.levels);
        const elapsed = Math.floor((now - startedAt) / 1000);
        setSeconds(elapsed);
        if (elapsed >= maxSeconds) { finish(true); return; }
      }
      current.frame = requestAnimationFrame(tick);
    };
    recorder.start(1000);
    setPhase("recording");
    current.frame = requestAnimationFrame(tick);
  };

  const recording = phase === "recording";
  return (
    <section className="pro-card pro-recorder" aria-labelledby="pro-recorder-title">
      <header className="pro-card-head">
        <div>
          <h3 id="pro-recorder-title">Record a tune</h3>
          <p className="pro-sub">Sing, hum or play. Up to {Math.floor(maxSeconds / 60)} minutes or {megabytes(limits.max_upload_bytes)}.</p>
        </div>
        <button type="button" className="pro-icon" onClick={() => { finish(false); onClose(); }} aria-label="Close recorder">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
      </header>
      <div className="pro-recorder-stage">
        <canvas ref={canvasRef} className="pro-recorder-canvas" aria-hidden="true" />
        {!recording && <p className="pro-recorder-idle">Press record when you're ready.</p>}
      </div>
      <p className="pro-recorder-time" role="timer" aria-live="off">{formatTime(seconds)}</p>
      <div className="pro-recorder-actions">
        {recording ? (
          <>
            <button type="button" className="pro-ghost" onClick={() => finish(false)}>Discard</button>
            <button type="button" className="pro-round pro-round-stop" onClick={() => finish(true)} aria-label="Stop and add recording">
              <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="2" /></svg>
            </button>
            <span className="pro-recorder-live" role="status">Recording…</span>
          </>
        ) : (
          <button type="button" className="pro-round" onClick={start} aria-label="Start recording">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5.5 11a6.5 6.5 0 0013 0M12 17.5V21" />
            </svg>
          </button>
        )}
      </div>
      {error && <p className="merger-error" role="alert">{error}</p>}
    </section>
  );
}
