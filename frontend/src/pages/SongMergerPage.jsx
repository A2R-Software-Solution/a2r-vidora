import { lazy, Suspense, useEffect, useId, useRef, useState, useSyncExternalStore } from "react";
import SiteLink from "../components/common/SiteLink";
import { createAudioMerge, getMergeDownload, getMergeLimits, listAudioMerges } from "../api/audioMergeApi";
import { refreshCredits, useCredits } from "../hooks/useCredits";
import { formatPreciseTime, formatTime } from "../utils/formatTime";
import { readAudioDuration } from "../utils/audioDecode";
import { CREDITS_MESSAGE, isYouTubeVideoUrl } from "../utils/videoInput";
import {
  CROSSFADE_CHOICES, DEFAULT_LIMITS, MIN_TRACKS, UPLOAD_EXTENSIONS, buildMergeRequest, isMergeExpired,
  isMergePending, megabytes, mergeCost, mergeError, mergeFailureMessage, parseTime, trackSeconds, validateMerge,
} from "../utils/audioMerge";
import { requireSignIn } from "../utils/authGate";
import "./SongMergerPage.css";

// The Pro editor (waveforms, recorder, player) loads only when someone switches to it.
const ProEditor = lazy(() => import("../components/merger/ProEditor"));

// Which editor the visitor last used, remembered on this device.
const MODE_KEY = "vidora-merger-mode";
const modeListeners = new Set();
const readMode = () => {
  try { return window.localStorage.getItem(MODE_KEY) === "pro" ? "pro" : "simple"; } catch { return "simple"; }
};
const subscribeMode = (listener) => { modeListeners.add(listener); return () => modeListeners.delete(listener); };
function saveMode(mode) {
  try { window.localStorage.setItem(MODE_KEY, mode); } catch { /* private browsing: the choice lasts for this visit only */ }
  modeListeners.forEach((listener) => listener());
}

const ICONS = {
  note: "M9 18V5l11-2v13M9 18a3 3 0 11-6 0 3 3 0 016 0zM20 16a3 3 0 11-6 0 3 3 0 016 0z",
  play: "M7 4.5v15l12-7.5z",
  stop: "M6 6h12v12H6z",
  trash: "M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3",
  up: "M12 19V5M6 11l6-6 6 6",
  down: "M12 5v14M6 13l6 6 6-6",
  wave: "M3 12h2M7 8v8M11 5v14M15 8v8M19 10v4M21 12h0",
  link: "M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1M14 10a4 4 0 00-5.7 0l-3 3a4 4 0 005.7 5.7l1-1",
  upload: "M12 16V4M7 9l5-5 5 5M4 16v4h16v-4",
  gear: "M12 15a3 3 0 100-6 3 3 0 000 6zM19 12l2-1-1-3-2 .3-1.3-1.3L17 5l-3-1-1 2h-2l-1-2-3 1 .3 2L6 8.3 4 8l-1 3 2 1v0l-2 1 1 3 2-.3 1.3 1.3L7 19l3 1 1-2h2l1 2 3-1-.3-2 1.3-1.3 2 .3 1-3z",
  doc: "M6 3h9l4 4v14H6zM14 3v5h5M9 12h7M9 16h7",
  clock: "M12 21a9 9 0 100-18 9 9 0 000 18zM12 7v5l3 2",
  bolt: "M13 2L4 14h7l-1 8 9-12h-7z",
  spark: "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 3v4M17 5h4",
  plus: "M12 5v14M5 12h14",
  external: "M14 4h6v6M20 4l-9 9M18 14v6H4V6h6",
};
function MIcon({ name, size = 18 }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={ICONS[name]} /></svg>;
}

let nextTrackId = 1;
const newTrack = () => ({ id: nextTrackId++, source: "youtube", url: "", file: null, duration: null, start: "0:00", end: "" });

// A YouTube link that opens at the track's start time.
function youtubeAt(url, start) {
  try {
    const link = new URL(url.trim());
    link.searchParams.set("t", `${Math.floor(start || 0)}s`);
    return link.toString();
  } catch { return ""; }
}

function TrackCard({ track, index, count, error, limits, onChange, onRemove, onMove }) {
  const uid = useId();
  const seconds = trackSeconds(track);
  const audio = useRef(null);
  const objectUrl = useRef("");
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const start = parseTime(track.start) ?? 0;
  const end = parseTime(track.end) ?? track.duration ?? 0;
  const span = Math.max(0, end - start);

  // A new or removed file: stop playback and free the old file's memory.
  useEffect(() => () => {
    audio.current?.pause();
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    objectUrl.current = "";
  }, [track.file]);

  const pickFile = async (event) => {
    const file = event.target.files?.[0] ?? null;
    event.target.value = "";
    if (!file) return;
    setPlaying(false);
    setPosition(0);
    onChange(track.id, { file, duration: null });
    const duration = await readAudioDuration(file);
    if (!duration) return;
    onChange(track.id, (current) => current.file === file ? {
      duration,
      end: current.end || formatTime(Math.min(Math.floor(duration), limits.max_segment_seconds)),
    } : {});
  };

  const togglePlay = () => {
    const player = audio.current;
    if (!player || !track.file) return;
    if (playing) { player.pause(); return; }
    if (!objectUrl.current) {
      objectUrl.current = URL.createObjectURL(track.file);
      player.src = objectUrl.current;
    }
    player.currentTime = start;
    player.play().catch(() => setPlaying(false));
  };
  const onTime = () => {
    const player = audio.current;
    if (!player) return;
    setPosition(Math.max(0, player.currentTime - start));
    if (end && player.currentTime >= end) player.pause();
  };

  const youtubeOk = track.source === "youtube" && isYouTubeVideoUrl(track.url);
  const progress = span ? Math.min(100, (position / span) * 100) : 0;
  const sources = [["youtube", "YouTube link", "link"], ["upload", "Upload audio", "upload"]];

  return (
    <li className="mg-track">
      <div className="mg-track-head">
        <span className="mg-track-icon"><MIcon name="note" /></span>
        <h3>Track {index + 1}</h3>
        <div className="mg-source" role="group" aria-label={`Track ${index + 1} source`}>
          {sources.map(([value, label, icon]) => (
            <button key={value} type="button" aria-pressed={track.source === value}
              onClick={() => { audio.current?.pause(); onChange(track.id, { source: value }); }}>
              <MIcon name={icon} size={15} />{label}
            </button>
          ))}
        </div>
        <div className="mg-track-tools">
          <button type="button" className="mg-icon-btn" onClick={() => onMove(track.id, -1)} disabled={index === 0}
            aria-label={`Move track ${index + 1} up`} title="Move up"><MIcon name="up" size={16} /></button>
          <button type="button" className="mg-icon-btn" onClick={() => onMove(track.id, 1)} disabled={index === count - 1}
            aria-label={`Move track ${index + 1} down`} title="Move down"><MIcon name="down" size={16} /></button>
          {track.source === "upload" ? (
            <button type="button" className="mg-btn" onClick={togglePlay} disabled={!track.file}>
              <span className="mg-btn-play"><MIcon name={playing ? "stop" : "play"} size={14} /></span>{playing ? "Stop" : "Preview"}
            </button>
          ) : (
            <a className={`mg-btn${youtubeOk ? "" : " is-disabled"}`} href={youtubeOk ? youtubeAt(track.url, start) : undefined}
              target="_blank" rel="noopener noreferrer" aria-disabled={!youtubeOk}>
              <span className="mg-btn-play"><MIcon name="play" size={14} /></span>Preview
            </a>
          )}
          <button type="button" className="mg-icon-btn" onClick={() => onRemove(track.id)} disabled={count <= MIN_TRACKS}
            aria-label={`Remove track ${index + 1}`} title="Remove"><MIcon name="trash" size={17} /></button>
        </div>
      </div>

      {track.source === "youtube" ? (
        <label className="mg-row mg-row--input" htmlFor={`${uid}-url`}>
          <span className="mg-row-icon"><MIcon name="link" /></span>
          <span className="sr-only">YouTube link</span>
          <input id={`${uid}-url`} type="url" inputMode="url" autoComplete="off" placeholder="Paste a YouTube link — https://www.youtube.com/watch?v=…"
            value={track.url} onChange={(event) => onChange(track.id, { url: event.target.value })} aria-invalid={!!error} />
        </label>
      ) : track.file ? (
        <div className="mg-row">
          <span className="mg-row-icon"><MIcon name="wave" /></span>
          <span className="mg-file"><strong>{track.file.name}</strong><span> · {megabytes(track.file.size)}</span></span>
          <button type="button" className="mg-play" onClick={togglePlay} aria-label={playing ? "Stop preview" : "Play preview"}>
            <MIcon name={playing ? "stop" : "play"} size={15} />
          </button>
          <span className="mg-progress" aria-hidden="true"><i style={{ width: `${progress}%` }} /></span>
          <span className="mg-time">{formatTime(Math.floor(position))} / {formatTime(Math.floor(span))}</span>
          <label className="mg-change">Change<input type="file" accept={UPLOAD_EXTENSIONS.join(",")} onChange={pickFile} className="sr-only" /></label>
        </div>
      ) : (
        <label className="mg-drop" aria-invalid={!!error}>
          <MIcon name="upload" size={22} />
          <span><strong>Choose an audio file</strong><small>MP3, WAV, M4A, FLAC… up to {megabytes(limits.max_upload_bytes)}</small></span>
          <input id={`${uid}-file`} type="file" accept={UPLOAD_EXTENSIONS.join(",")} onChange={pickFile} className="sr-only" />
        </label>
      )}
      <audio ref={audio} preload="none" onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onTimeUpdate={onTime} hidden />

      <div className="mg-times">
        <div className="mg-field">
          <label htmlFor={`${uid}-start`}>From</label>
          <input id={`${uid}-start`} type="text" autoComplete="off" placeholder="1:00" value={track.start}
            onChange={(event) => onChange(track.id, { start: event.target.value })} aria-invalid={!!error} />
        </div>
        <div className="mg-field">
          <label htmlFor={`${uid}-end`}>To</label>
          <input id={`${uid}-end`} type="text" autoComplete="off" placeholder="2:40" value={track.end}
            onChange={(event) => onChange(track.id, { end: event.target.value })} aria-invalid={!!error} />
        </div>
        <p className="mg-length" aria-live="polite">
          <MIcon name="clock" size={15} />{seconds ? formatPreciseTime(seconds) : "Use mm:ss"}
        </p>
      </div>
      {error && <p className="merger-error" role="alert">{error}</p>}
    </li>
  );
}

function MergeCard({ job }) {
  const [preview, setPreview] = useState("");
  const [action, setAction] = useState("");
  const [error, setError] = useState("");
  const busy = useRef(false);
  const expired = isMergeExpired(job);

  const openMedia = async (download) => {
    if (busy.current) return;
    busy.current = true;
    setAction(download ? "download" : "preview");
    setError("");
    try {
      // A fresh signed link for every action.
      const { data } = await getMergeDownload(job.id, download);
      if (download) {
        const link = document.createElement("a");
        link.href = data.url;
        link.rel = "noopener";
        link.download = `vidora-merged.${job.output_format}`;
        document.body.appendChild(link);
        link.click();
        link.remove();
      } else setPreview(data.url);
    } catch (err) {
      setError(mergeError(err));
    } finally {
      busy.current = false;
      setAction("");
    }
  };

  const tone = expired ? "muted" : job.status === "completed" ? "done" : isMergePending(job) ? "busy" : "failed";
  const status = expired ? "Expired" : job.status === "queued" ? "Queued — waiting to start"
    : job.status === "processing" ? "Merging your tracks…" : job.status === "completed" ? "Ready to download"
    : mergeFailureMessage(job.error_code);
  return (
    <li className="mg-result">
      <span className="mg-track-icon"><MIcon name="wave" /></span>
      <div className="mg-result-body">
        <div className="mg-result-head">
          <h3>{job.tracks.length} tracks · {formatTime(job.total_seconds)} · {job.output_format.toUpperCase()}</h3>
          <span className="mg-cost">{job.credit_cost} credits</span>
        </div>
        <p className={`mg-status mg-status--${tone}`} role="status">{status}</p>
        <p className="mg-hint">{expired ? "Expired" : "Available until"} {new Date(job.expires_at).toLocaleString()}</p>
        {!expired && job.status === "completed" && (
          <div className="mg-actions">
            <button type="button" className="mg-btn" onClick={() => openMedia(false)} disabled={!!action}>
              <span className="mg-btn-play"><MIcon name="play" size={14} /></span>{action === "preview" ? "Loading…" : "Listen"}
            </button>
            <button type="button" className="mg-btn mg-btn--solid" onClick={() => openMedia(true)} disabled={!!action}>
              {action === "download" ? "Preparing…" : `Download ${job.output_format.toUpperCase()}`}
            </button>
          </div>
        )}
        {preview && !expired && <audio className="mg-audio" src={preview} controls preload="metadata" aria-label="Merged song preview"
          onError={() => { setPreview(""); setError("The listen link may have expired. Click Listen to load a fresh one."); }} />}
        {error && <p className="merger-error" role="alert">{error}</p>}
      </div>
    </li>
  );
}

function Illustration() {
  return (
    <aside className="mg-art">
      <svg className="mg-art-svg" viewBox="0 0 240 230" aria-hidden="true">
        <defs>
          <linearGradient id="mg-cup" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#ffb487" /><stop offset="1" stopColor="#f06a2c" /></linearGradient>
          <linearGradient id="mg-band" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#ffc7a5" /><stop offset="1" stopColor="#f58a52" /></linearGradient>
          <radialGradient id="mg-shadow"><stop offset="0" stopColor="#e9a27a" stopOpacity=".45" /><stop offset="1" stopColor="#e9a27a" stopOpacity="0" /></radialGradient>
        </defs>
        <g className="mg-art-bars" fill="#f7b691">
          {[34, 58, 40, 80, 52, 96, 62, 44, 70, 38].map((height, i) => (
            <rect key={i} x={172 + (i % 5) * 9} y={110 - height / 2 + (i > 4 ? 30 : -18)} width="4" height={height / 1.6} rx="2" opacity={0.35 + (i % 3) * 0.15} />
          ))}
          {[30, 52, 24, 44].map((height, i) => <rect key={`l${i}`} x={14 + i * 9} y={140 - height / 2} width="4" height={height} rx="2" opacity=".4" />)}
        </g>
        <ellipse cx="120" cy="212" rx="78" ry="12" fill="url(#mg-shadow)" />
        <path d="M58 140V112a62 62 0 01124 0v28" fill="none" stroke="url(#mg-band)" strokeWidth="16" strokeLinecap="round" />
        <path d="M58 140V112a62 62 0 01124 0v28" fill="none" stroke="#fff" strokeOpacity=".35" strokeWidth="4" strokeLinecap="round" />
        <rect x="34" y="122" width="48" height="76" rx="24" fill="url(#mg-cup)" />
        <rect x="158" y="122" width="48" height="76" rx="24" fill="url(#mg-cup)" />
        <rect x="64" y="132" width="22" height="56" rx="11" fill="#e2591d" />
        <rect x="154" y="132" width="22" height="56" rx="11" fill="#e2591d" />
        <ellipse cx="50" cy="146" rx="7" ry="13" fill="#fff" opacity=".35" />
        <ellipse cx="174" cy="146" rx="7" ry="13" fill="#fff" opacity=".35" />
        <g fill="#f59a68">
          <path d="M40 40v26a8 8 0 11-4-7V36l20-5v6z" opacity=".75" />
          <path d="M196 62v18a6 6 0 11-3-5V58l14-3v4z" opacity=".55" />
        </g>
      </svg>
      <h2>Mix. Merge. Create.</h2>
      <p>Combine your favourite audio parts effortlessly.</p>
    </aside>
  );
}

// A guest's (empty) history; one array so effects that depend on it stay stable.
const NOTHING = [];

export default function SongMergerPage({ signedIn = false }) {
  const [limits, setLimits] = useState(null);
  const [tracks, setTracks] = useState(() => [newTrack(), newTrack()]);
  const [options, setOptions] = useState({ outputFormat: "mp3", crossfade: 0 });
  const [consent, setConsent] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [notice, setNotice] = useState("");
  const [loadedMerges, setMerges] = useState(null);
  const merges = signedIn ? loadedMerges : NOTHING;
  const [historyError, setHistoryError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const wasPending = useRef(false);
  const submitBusy = useRef(false);
  const credits = useCredits();
  const rules = limits ?? DEFAULT_LIMITS;
  const enabled = limits ? limits.enabled : true;
  const savedMode = useSyncExternalStore(subscribeMode, readMode, () => "simple");
  const mode = rules.pro_enabled ? savedMode : "simple";

  useEffect(() => {
    const controller = new AbortController();
    getMergeLimits(controller.signal).then(({ data }) => setLimits({ ...DEFAULT_LIMITS, ...data }))
      .catch(() => { if (!controller.signal.aborted) setLimits(DEFAULT_LIMITS); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    // Merges belong to an account; a guest has none to list.
    if (!enabled || !signedIn) return undefined;
    const controller = new AbortController();
    let timer;
    const poll = async () => {
      let delay = 30000;
      try {
        const { data } = await listAudioMerges(controller.signal);
        if (controller.signal.aborted) return;
        setMerges(data.items);
        setHistoryError("");
        const pending = data.items.some(isMergePending);
        // A finished merge settles its credits; a failed one returns them.
        if (wasPending.current && !pending) void refreshCredits();
        wasPending.current = pending;
        if (pending) delay = 4000;
      } catch (err) {
        if (controller.signal.aborted) return;
        setHistoryError(mergeError(err));
      }
      if (!controller.signal.aborted) timer = setTimeout(poll, delay);
    };
    poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [enabled, refresh, signedIn]);

  const update = (id, patch) => setTracks((current) => current.map((track) =>
    track.id === id ? { ...track, ...(typeof patch === "function" ? patch(track) : patch) } : track));
  const remove = (id) => setTracks((current) => current.filter((track) => track.id !== id));
  const move = (id, step) => setTracks((current) => {
    const from = current.findIndex((track) => track.id === id);
    const to = from + step;
    if (to < 0 || to >= current.length) return current;
    const next = [...current];
    [next[from], next[to]] = [next[to], next[from]];
    return next;
  });

  const { trackErrors, formError } = validateMerge(tracks, options, rules);
  const cost = mergeCost(tracks, rules);
  const total = tracks.reduce((sum, track) => sum + trackSeconds(track), 0);
  const hasErrors = !!formError || Object.keys(trackErrors).length > 0;
  const affordable = cost == null || credits == null || credits.available >= cost;
  const fades = CROSSFADE_CHOICES.filter((seconds) => seconds > 0 && seconds <= rules.max_crossfade_seconds);
  const blend = options.crossfade > 0;
  const setOption = (patch) => setOptions((current) => ({ ...current, ...patch }));

  const addMerge = (job) => setMerges((previous) => [job, ...(previous || []).filter((item) => item.id !== job.id)]);
  // After any attempt: the server may have accepted a job whose response was lost.
  const settle = () => {
    setRefresh((value) => value + 1);
    void refreshCredits();
  };

  const submit = async (event) => {
    event.preventDefault();
    if (submitBusy.current) return;
    setAttempted(true);
    setNotice("");
    if (hasErrors) { setSubmitError(""); return; }
    if (!consent) { setSubmitError("Please confirm you have the rights to use this audio."); return; }
    if (!requireSignIn()) return;
    if (!affordable) { setSubmitError(CREDITS_MESSAGE); return; }
    submitBusy.current = true;
    setSubmitting(true);
    setSubmitError("");
    try {
      const { data: job } = await createAudioMerge(buildMergeRequest(tracks, options));
      addMerge(job);
      setNotice("Your merge has started. It appears in Your merges below when it's ready.");
    } catch (err) {
      setSubmitError(mergeError(err));
    } finally {
      settle();
      submitBusy.current = false;
      setSubmitting(false);
    }
  };

  return (
    <article className="public-page merger-page">
      <header className="mg-header">
        <p className="mg-eyebrow">Song Merger</p>
        <h1>Your best parts. <span>One perfect song.</span></h1>
        <p className="mg-intro">Merge audio tracks, choose your options and create a seamless final track.</p>
        {enabled && rules.pro_enabled && (
          <div className="merger-modes" role="group" aria-label="Editor">
            {[["simple", "Simple"], ["pro", "Pro editor"]].map(([value, label]) => (
              <button key={value} type="button" aria-pressed={mode === value} onClick={() => saveMode(value)}>{label}</button>
            ))}
          </div>
        )}
      </header>

      {!enabled ? (
        <p className="merger-note" role="status">Song Merger is launching soon. Please check back shortly.</p>
      ) : mode === "pro" ? (
        <Suspense fallback={<p className="mg-hint" role="status">Loading the editor…</p>}>
          <ProEditor rules={rules} credits={credits} onMerged={addMerge} onSettled={settle} />
        </Suspense>
      ) : (
        <form className="mg-shell" onSubmit={submit} noValidate>
          <Illustration />
          <div className="mg-main">
            <section aria-label="Your tracks">
              <ol className="mg-tracks">
                {tracks.map((track, index) => (
                  <TrackCard key={track.id} track={track} index={index} count={tracks.length} limits={rules}
                    error={attempted ? trackErrors[track.id] : ""} onChange={update} onRemove={remove} onMove={move} />
                ))}
              </ol>
              <button type="button" className="mg-add" onClick={() => setTracks((current) => [...current, newTrack()])}
                disabled={tracks.length >= rules.max_tracks}>
                <MIcon name="plus" size={16} /> Add track {tracks.length >= rules.max_tracks ? `(max ${rules.max_tracks})` : ""}
              </button>
            </section>

            <section className="mg-section" aria-labelledby="mg-options-title">
              <h2 id="mg-options-title"><MIcon name="gear" size={20} /> Options</h2>
              <div className="mg-options">
                <div className="mg-field">
                  <label htmlFor="mg-mode">Merge Mode</label>
                  <select id="mg-mode" value={blend ? "blend" : "sequence"}
                    onChange={(event) => setOption({ crossfade: event.target.value === "blend" ? fades[0] ?? 0 : 0 })}>
                    <option value="sequence">One after another</option>
                    {fades.length > 0 && <option value="blend">Blend together</option>}
                  </select>
                </div>
                <div className="mg-field">
                  <label htmlFor="mg-fade">Fade Effect</label>
                  <select id="mg-fade" value={options.crossfade} disabled={!blend}
                    onChange={(event) => setOption({ crossfade: Number(event.target.value) })}>
                    {!blend && <option value={0}>Off (pick Blend together)</option>}
                    {blend && fades.map((seconds) => <option key={seconds} value={seconds}>{seconds} sec</option>)}
                  </select>
                </div>
                <div className="mg-field">
                  <label htmlFor="mg-format">Output Format</label>
                  <select id="mg-format" value={options.outputFormat} onChange={(event) => setOption({ outputFormat: event.target.value })}>
                    {rules.output_formats.map((format) => <option key={format} value={format}>{format.toUpperCase()}</option>)}
                  </select>
                </div>
              </div>
            </section>

            <section className="mg-section" aria-labelledby="mg-summary-title">
              <h2 id="mg-summary-title"><MIcon name="doc" size={20} /> Summary</h2>
              <div className="mg-summary">
                <dl>
                  <div><dt><MIcon name="clock" size={17} /> Total Duration:</dt><dd>{total ? formatPreciseTime(total) : "Add links and times"}</dd></div>
                  <div><dt><MIcon name="wave" size={17} /> Tracks:</dt><dd>{tracks.length}</dd></div>
                  <div><dt><MIcon name="bolt" size={17} /> Cost:</dt><dd>{cost == null ? "—" : `${cost} credits`}</dd></div>
                </dl>
                <p className="mg-callout">
                  <MIcon name="spark" size={16} />
                  <span>1 credit per minute, plus {rules.extra_track_credits} per extra track. Credits come back if the merge fails on our side.</span>
                </p>
              </div>
              {!affordable && <p className="merger-note">You need {cost} credits. Free credits renew at midnight IST. <SiteLink href="/pricing">See pricing</SiteLink></p>}
              {attempted && formError && <p className="merger-error" role="alert">{formError}</p>}
              <label className="merger-consent">
                <input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} />
                I own this audio or have the right to use it, and I will only use the result as the law and the source&apos;s terms allow.
              </label>
              {submitError && <p className="merger-error" role="alert">{submitError}</p>}
              {notice && <p className="merger-success" role="status">{notice}</p>}
              <button type="submit" className="mg-submit" disabled={submitting}>
                <MIcon name="spark" size={20} />{submitting ? "Uploading…" : "Merge Tracks"}
              </button>
            </section>
          </div>
        </form>
      )}

      {enabled && (
        <section className="mg-history" aria-labelledby="mg-history-title">
          <h2 id="mg-history-title">Your merges</h2>
          {historyError && (
            <p className="merger-error" role="alert">{historyError}{" "}
              <button type="button" className="merger-link" onClick={() => setRefresh((value) => value + 1)}>Refresh</button>
            </p>
          )}
          {merges && merges.length === 0 && !historyError && <p className="mg-empty">Nothing here yet. Your finished merges stay available for a limited time.</p>}
          {merges && merges.length > 0 && <ul className="mg-results">{merges.map((job) => <MergeCard key={job.id} job={job} />)}</ul>}
        </section>
      )}
    </article>
  );
}
