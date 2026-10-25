import { useEffect, useId, useRef, useState } from "react";
import SiteLink from "../components/common/SiteLink";
import { createAudioMerge, getMergeDownload, getMergeLimits, listAudioMerges } from "../api/audioMergeApi";
import { refreshCredits, useCredits } from "../hooks/useCredits";
import { formatTime } from "../utils/formatTime";
import { CREDITS_MESSAGE } from "../utils/videoInput";
import {
  CROSSFADE_CHOICES, DEFAULT_LIMITS, MIN_TRACKS, UPLOAD_EXTENSIONS, buildMergeRequest, isMergeExpired,
  isMergePending, megabytes, mergeCost, mergeError, mergeFailureMessage, trackSeconds, validateMerge,
} from "../utils/audioMerge";
import "./SongMergerPage.css";

let nextTrackId = 1;
const newTrack = () => ({ id: nextTrackId++, source: "youtube", url: "", file: null, duration: null, start: "0:00", end: "" });

// Browsers can tell us an uploaded file's length, which lets us check the range early.
function readAudioDuration(file) {
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

function TrackCard({ track, index, count, error, limits, onChange, onRemove, onMove }) {
  const uid = useId();
  const seconds = trackSeconds(track);
  const pickFile = async (event) => {
    const file = event.target.files?.[0] ?? null;
    onChange(track.id, { file, duration: null });
    if (!file) return;
    const duration = await readAudioDuration(file);
    if (!duration) return;
    onChange(track.id, (current) => current.file === file ? {
      duration,
      end: current.end || formatTime(Math.min(Math.floor(duration), limits.max_segment_seconds)),
    } : {});
  };
  return (
    <li className="merger-track">
      <div className="merger-track-head">
        <h3>Track {index + 1}</h3>
        <div className="merger-track-tools">
          <button type="button" onClick={() => onMove(track.id, -1)} disabled={index === 0} aria-label={`Move track ${index + 1} up`}>↑</button>
          <button type="button" onClick={() => onMove(track.id, 1)} disabled={index === count - 1} aria-label={`Move track ${index + 1} down`}>↓</button>
          <button type="button" onClick={() => onRemove(track.id)} disabled={count <= MIN_TRACKS} aria-label={`Remove track ${index + 1}`}>Remove</button>
        </div>
      </div>

      <fieldset className="merger-source">
        <legend>Source</legend>
        {[["youtube", "YouTube link"], ["upload", "Upload audio"]].map(([value, label]) => (
          <label key={value}>
            <input type="radio" name={`${uid}-source`} value={value} checked={track.source === value}
              onChange={() => onChange(track.id, { source: value })} />
            {label}
          </label>
        ))}
      </fieldset>

      {track.source === "youtube" ? (
        <div className="merger-field">
          <label htmlFor={`${uid}-url`}>YouTube link</label>
          <input id={`${uid}-url`} type="url" inputMode="url" autoComplete="off" placeholder="https://www.youtube.com/watch?v=…"
            value={track.url} onChange={(event) => onChange(track.id, { url: event.target.value })} aria-invalid={!!error} />
        </div>
      ) : (
        <div className="merger-field">
          <label htmlFor={`${uid}-file`}>Audio file (up to {megabytes(limits.max_upload_bytes)})</label>
          <input id={`${uid}-file`} type="file" accept={UPLOAD_EXTENSIONS.join(",")} onChange={pickFile} aria-invalid={!!error} />
          {track.file && <p className="merger-hint">{track.file.name} · {megabytes(track.file.size)}{track.duration ? ` · ${formatTime(Math.floor(track.duration))} long` : ""}</p>}
        </div>
      )}

      <div className="merger-times">
        <div className="merger-field">
          <label htmlFor={`${uid}-start`}>From</label>
          <input id={`${uid}-start`} type="text" autoComplete="off" placeholder="1:00" value={track.start}
            onChange={(event) => onChange(track.id, { start: event.target.value })} aria-invalid={!!error} />
        </div>
        <div className="merger-field">
          <label htmlFor={`${uid}-end`}>To</label>
          <input id={`${uid}-end`} type="text" autoComplete="off" placeholder="2:40" value={track.end}
            onChange={(event) => onChange(track.id, { end: event.target.value })} aria-invalid={!!error} />
        </div>
        <p className="merger-length" aria-live="polite">{seconds ? `Length ${formatTime(seconds)}` : "Use mm:ss"}</p>
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

  const status = expired ? "Expired" : job.status === "queued" ? "Queued — waiting to start"
    : job.status === "processing" ? "Merging your tracks…" : job.status === "completed" ? "Ready to download"
    : mergeFailureMessage(job.error_code);
  return (
    <li className="merger-result">
      <div className="merger-result-head">
        <h3>{job.tracks.length} tracks · {formatTime(job.total_seconds)} · {job.output_format.toUpperCase()}</h3>
        <span>{job.credit_cost} credits</span>
      </div>
      <p className="merger-status" role="status">{status}</p>
      <p className="merger-hint">{expired ? "Expired" : "Available until"} {new Date(job.expires_at).toLocaleString()}</p>
      {!expired && job.status === "completed" && (
        <div className="merger-actions">
          <button type="button" onClick={() => openMedia(false)} disabled={!!action}>{action === "preview" ? "Loading…" : "Listen"}</button>
          <button type="button" onClick={() => openMedia(true)} disabled={!!action}>{action === "download" ? "Preparing…" : `Download ${job.output_format.toUpperCase()}`}</button>
        </div>
      )}
      {preview && !expired && <audio className="merger-audio" src={preview} controls preload="metadata" aria-label="Merged song preview"
        onError={() => { setPreview(""); setError("The listen link may have expired. Click Listen to load a fresh one."); }} />}
      {error && <p className="merger-error" role="alert">{error}</p>}
    </li>
  );
}

export default function SongMergerPage({ signedIn = false }) {
  const [limits, setLimits] = useState(null);
  const [tracks, setTracks] = useState(() => [newTrack(), newTrack()]);
  const [options, setOptions] = useState({ outputFormat: "mp3", crossfade: 0 });
  const [consent, setConsent] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [notice, setNotice] = useState("");
  const [merges, setMerges] = useState(null);
  const [historyError, setHistoryError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const wasPending = useRef(false);
  const submitBusy = useRef(false);
  const credits = useCredits();
  const rules = limits ?? DEFAULT_LIMITS;
  const enabled = limits ? limits.enabled : true;

  useEffect(() => {
    const controller = new AbortController();
    getMergeLimits(controller.signal).then(({ data }) => setLimits({ ...DEFAULT_LIMITS, ...data }))
      .catch(() => { if (!controller.signal.aborted) setLimits(DEFAULT_LIMITS); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!enabled) return undefined;
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

  const submit = async (event) => {
    event.preventDefault();
    if (submitBusy.current) return;
    setAttempted(true);
    setNotice("");
    if (hasErrors) { setSubmitError(""); return; }
    if (!consent) { setSubmitError("Please confirm you have the rights to use this audio."); return; }
    if (!affordable) { setSubmitError(CREDITS_MESSAGE); return; }
    submitBusy.current = true;
    setSubmitting(true);
    setSubmitError("");
    try {
      const { data: job } = await createAudioMerge(buildMergeRequest(tracks, options));
      setMerges((previous) => [job, ...(previous || []).filter((item) => item.id !== job.id)]);
      setNotice("Your merge has started. It appears below when it's ready.");
    } catch (err) {
      setSubmitError(mergeError(err));
    } finally {
      // Reconcile a lost response: the server may have accepted the job.
      setRefresh((value) => value + 1);
      void refreshCredits();
      submitBusy.current = false;
      setSubmitting(false);
    }
  };

  return (
    <article className="public-page merger-page">
      <header className="public-header">
        <p className="public-eyebrow">Song Merger</p>
        <h1>Join the best parts of your songs into one.</h1>
        <p className="public-intro">
          Pick a section of each YouTube video or audio file, put them in order, and download one merged song.
        </p>
        {credits && <p className="merger-balance" role="status">You have <strong>{credits.available} credits</strong> available.</p>}
      </header>

      {!enabled ? (
        <p className="merger-note" role="status">Song Merger is launching soon. Please check back shortly.</p>
      ) : (
        <form className="merger-form" onSubmit={submit} noValidate>
          <section aria-labelledby="merger-tracks-title">
            <h2 id="merger-tracks-title">Your tracks</h2>
            <ol className="merger-tracks">
              {tracks.map((track, index) => (
                <TrackCard key={track.id} track={track} index={index} count={tracks.length} limits={rules}
                  error={attempted ? trackErrors[track.id] : ""} onChange={update} onRemove={remove} onMove={move} />
              ))}
            </ol>
            <button type="button" className="merger-add" onClick={() => setTracks((current) => [...current, newTrack()])}
              disabled={tracks.length >= rules.max_tracks}>
              + Add track {tracks.length >= rules.max_tracks ? `(max ${rules.max_tracks})` : ""}
            </button>
          </section>

          <section className="merger-options" aria-labelledby="merger-options-title">
            <h2 id="merger-options-title">Options</h2>
            <div className="merger-options-grid">
              <div className="merger-field">
                <label htmlFor="merger-format">File type</label>
                <select id="merger-format" value={options.outputFormat}
                  onChange={(event) => setOptions((current) => ({ ...current, outputFormat: event.target.value }))}>
                  {rules.output_formats.map((format) => <option key={format} value={format}>{format.toUpperCase()}</option>)}
                </select>
              </div>
              <div className="merger-field">
                <label htmlFor="merger-crossfade">Blend between tracks</label>
                <select id="merger-crossfade" value={options.crossfade}
                  onChange={(event) => setOptions((current) => ({ ...current, crossfade: Number(event.target.value) }))}>
                  {CROSSFADE_CHOICES.filter((seconds) => seconds <= rules.max_crossfade_seconds).map((seconds) => (
                    <option key={seconds} value={seconds}>{seconds ? `${seconds} second crossfade` : "No blend (play one after another)"}</option>
                  ))}
                </select>
              </div>
            </div>
          </section>

          <section className="merger-summary" aria-labelledby="merger-summary-title">
            <h2 id="merger-summary-title">Summary</h2>
            <dl>
              <div><dt>Tracks</dt><dd>{tracks.length}</dd></div>
              <div><dt>Merged length</dt><dd>{total ? formatTime(total) : "—"}</dd></div>
              <div><dt>Cost</dt><dd>{cost == null ? "—" : `${cost} credits`}</dd></div>
            </dl>
            <p className="merger-hint">1 credit per minute of selected audio, plus {rules.extra_track_credits} per extra track. Credits are returned if the merge fails on our side.</p>
            {!affordable && <p className="merger-note">You need {cost} credits. Free credits renew at midnight IST. <SiteLink href="/pricing">See pricing</SiteLink></p>}
            {attempted && formError && <p className="merger-error" role="alert">{formError}</p>}
            <label className="merger-consent">
              <input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} />
              I own this audio or have the right to use it, and I will only use the result as the law and the source's terms allow.
            </label>
            {submitError && <p className="merger-error" role="alert">{submitError}</p>}
            {notice && <p className="merger-success" role="status">{notice}</p>}
            <button type="submit" className="merger-submit" disabled={submitting}>
              {submitting ? "Uploading…" : "Merge tracks"}
            </button>
          </section>
        </form>
      )}

      {enabled && (
        <section className="merger-history" aria-labelledby="merger-history-title">
          <h2 id="merger-history-title">Your merges</h2>
          {historyError && (
            <p className="merger-error" role="alert">{historyError}{" "}
              <button type="button" className="merger-link" onClick={() => setRefresh((value) => value + 1)}>Refresh</button>
            </p>
          )}
          {merges && merges.length === 0 && !historyError && <p className="merger-hint">Nothing here yet. Your finished merges stay available for a limited time.</p>}
          {merges && merges.length > 0 && <ul className="merger-results">{merges.map((job) => <MergeCard key={job.id} job={job} />)}</ul>}
        </section>
      )}
    </article>
  );
}
