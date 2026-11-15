import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import SiteLink from "../common/SiteLink";
import { createAudioMerge, createAudioSource, getAudioSource } from "../../api/audioMergeApi";
import { decodeAudioFile } from "../../utils/audioDecode";
import { formatPreciseTime, formatTime } from "../../utils/formatTime";
import { CREDITS_MESSAGE } from "../../utils/videoInput";
import { CROSSFADE_CHOICES, UPLOAD_EXTENSIONS, megabytes, mergeError, parseTime } from "../../utils/audioMerge";
import {
  FADE_CHOICES, buildProRequest, fitRange, moveEdge, partSeconds, proCost, songFromSource,
  sourceFailureMessage, totalSeconds, validateFile, validateLink, validatePro, zoomLevels,
} from "../../utils/proMerge";
import { EditorPlayer } from "./editorPlayer";
import Recorder from "./Recorder";
import Waveform from "./Waveform";
import "./ProEditor.css";

const MAX_SONGS = 10;
// Parts are placed exactly where the user drags: no snapping, to the millisecond.
const FREE_STEP = 0.001;
const POLL_MS = 2500;
const KIND_LABELS = { youtube: "YouTube", upload: "Uploaded file", mic: "Recording" };
let nextId = 1;

const patchById = (items, id, patch) => items.map((item) => (item.id === id ? { ...item, ...patch } : item));

const Icon = ({ children }) => <svg viewBox="0 0 24 24" aria-hidden="true">{children}</svg>;
const PlayIcon = () => <Icon><path className="fill" d="M8 5.5v13l11-6.5z" /></Icon>;
const PauseIcon = () => <Icon><path className="fill" d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" /></Icon>;
const CloseIcon = () => <Icon><path d="M6 6l12 12M18 6L6 18" /></Icon>;

// A time the user can type ("1:30", or "1:30.25" for fractions of a second); it is applied when they leave the field.
function TimeField({ id, label, value, onCommit }) {
  const [text, setText] = useState(null);
  const commit = () => {
    const seconds = parseTime(text);
    if (text != null && seconds != null && seconds !== value) onCommit(seconds);
    setText(null);
  };
  return (
    <label className="pro-time" htmlFor={id}>
      <span>{label}</span>
      <input id={id} type="text" inputMode="decimal" autoComplete="off" value={text ?? formatPreciseTime(value)}
        onChange={(event) => setText(event.target.value)} onBlur={commit}
        onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); event.currentTarget.blur(); } }} />
    </label>
  );
}

function SongCard({ song, parts, numbers, limits, player, playing, canAdd, onPatch, onRemove, onCreatePart, onChangePart, onSelectPart }) {
  const ready = song.status === "ready";
  const levels = ready ? zoomLevels(song.duration) : [1];
  const level = levels.indexOf(song.zoom);
  const zoomBy = (step) => onPatch(song.id, { zoom: levels[Math.min(Math.max(level + step, 0), levels.length - 1)] });
  return (
    <section className="pro-card pro-song" aria-label={song.name}>
      <header className="pro-card-head">
        <div className="pro-song-title">
          <h3>{song.name}</h3>
          <p className="pro-sub">{KIND_LABELS[song.kind]}{ready ? ` · ${formatTime(Math.floor(song.duration))}` : ""}</p>
        </div>
        <button type="button" className="pro-icon" onClick={() => onRemove(song.id)} aria-label={`Remove ${song.name}`}><CloseIcon /></button>
      </header>

      {song.status === "loading" && (
        <>
          <div className="pro-skeleton" aria-hidden="true" />
          <p className="pro-sub" role="status">
            {song.kind === "youtube" ? "Loading this song from YouTube. It usually takes under a minute." : "Reading your audio…"}
          </p>
        </>
      )}
      {song.status === "error" && <p className="merger-error" role="alert">{song.error}</p>}
      {ready && (
        <>
          <p className="pro-sub">Drag across the wave to pick a part. Click anywhere to listen from there. Ctrl + scroll to zoom in for fine cuts.</p>
          <Waveform song={song} parts={parts} numbers={numbers} limits={limits} player={player} canAdd={canAdd}
            snap={FREE_STEP} zoom={song.zoom} onZoom={zoomBy}
            onCreate={(range) => onCreatePart(song.id, range)} onChange={onChangePart} onSelect={onSelectPart} />
          {!song.peaks && <p className="pro-sub">Your browser can't draw this file's wave, but you can still pick parts and listen.</p>}
          <div className="pro-song-controls">
            <button type="button" className="pro-round pro-round-small" onClick={() => player.toggleSong(song.id)}
              aria-label={playing ? `Pause ${song.name}` : `Listen to ${song.name}`}>
              {playing ? <PauseIcon /> : <PlayIcon />}
            </button>
            <label className="pro-volume">
              <span>Volume</span>
              <input type="range" min="0" max="100" step="1" value={song.volume} style={{ "--fill": `${song.volume}%` }}
                onChange={(event) => onPatch(song.id, { volume: Number(event.target.value) })} />
              <output>{song.volume}</output>
            </label>
            <button type="button" className="pro-ghost" disabled={!canAdd}
              onClick={() => onCreatePart(song.id, fitRange(0, song.duration, song.duration, limits.max_segment_seconds, "start", 0.001))}>
              Use whole song
            </button>
          </div>
        </>
      )}
    </section>
  );
}

function PartRow({ part, index, count, song, error, active, limits, player, onChange, onMove, onRemove }) {
  // Typed times are taken as written, to the millisecond, whatever the snap setting.
  const type = (edge, seconds) => onChange(part.id, moveEdge(part, edge, seconds, song.duration, limits.max_segment_seconds, 0.001));
  return (
    <li className={`pro-part${active ? " is-active" : ""}`}>
      <div className="pro-part-head">
        <span className="pro-part-number">{index + 1}</span>
        <div className="pro-part-name">
          <strong>{song.name}</strong>
          <span>{formatPreciseTime(partSeconds(part))} long</span>
        </div>
        <div className="pro-part-tools">
          <button type="button" className="pro-icon" onClick={() => player.playSequence(index)} aria-label={`Listen from part ${index + 1}`}><PlayIcon /></button>
          <button type="button" className="pro-icon" onClick={() => onMove(part.id, -1)} disabled={index === 0} aria-label={`Move part ${index + 1} earlier`}>
            <Icon><path d="M12 19V5M6 11l6-6 6 6" /></Icon>
          </button>
          <button type="button" className="pro-icon" onClick={() => onMove(part.id, 1)} disabled={index === count - 1} aria-label={`Move part ${index + 1} later`}>
            <Icon><path d="M12 5v14M6 13l6 6 6-6" /></Icon>
          </button>
          <button type="button" className="pro-icon" onClick={() => onRemove(part.id)} aria-label={`Remove part ${index + 1}`}><CloseIcon /></button>
        </div>
      </div>
      <div className="pro-part-fields">
        <TimeField id={`part-${part.id}-from`} label="From" value={part.start} onCommit={(seconds) => type("start", seconds)} />
        <TimeField id={`part-${part.id}-to`} label="To" value={part.end} onCommit={(seconds) => type("end", seconds)} />
        {[["fadeIn", "Fade in"], ["fadeOut", "Fade out"]].map(([field, label]) => (
          <label className="pro-time" key={field} htmlFor={`part-${part.id}-${field}`}>
            <span>{label}</span>
            <select id={`part-${part.id}-${field}`} value={part[field]}
              onChange={(event) => onChange(part.id, { [field]: Number(event.target.value) })}>
              {FADE_CHOICES.filter((seconds) => seconds <= limits.max_fade_seconds).map((seconds) => (
                <option key={seconds} value={seconds}>{seconds ? `${seconds}s` : "Off"}</option>
              ))}
            </select>
          </label>
        ))}
      </div>
      {error && <p className="merger-error" role="alert">{error}</p>}
    </li>
  );
}

function Transport({ player, playing, total }) {
  const timeRef = useRef(null);
  const rangeRef = useRef(null);
  useEffect(() => player.attachTransport({ time: timeRef.current, range: rangeRef.current }), [player]);
  return (
    <div className="pro-transport" role="group" aria-label="Listen to your mix">
      <div className="pro-transport-line">
        <span ref={timeRef} className="pro-clock">00:00</span>
        <input ref={rangeRef} type="range" min="0" max={Math.max(total, 0.1)} step="0.01" defaultValue="0"
          aria-label="Position in your mix" onChange={(event) => player.seekSequence(Number(event.target.value))} />
        <span className="pro-clock">{formatTime(total)}</span>
      </div>
      <div className="pro-transport-buttons">
        <button type="button" className="pro-icon" onClick={() => player.step(-1)} aria-label="Previous part">
          <Icon><path className="fill" d="M11 12l8-6v12zM4 12l8-6v12z" /></Icon>
        </button>
        <button type="button" className="pro-round" onClick={() => player.toggle()}
          aria-label={playing ? "Pause" : "Play your mix"}>
          {playing ? <PauseIcon /> : <PlayIcon />}
        </button>
        <button type="button" className="pro-icon" onClick={() => player.step(1)} aria-label="Next part">
          <Icon><path className="fill" d="M13 12L5 6v12zM20 12l-8-6v12z" /></Icon>
        </button>
      </div>
    </div>
  );
}

// The Pro editor: load songs, pick parts on their waveforms, arrange them and
// merge. It sends the same request as Simple mode, so it costs the same.
export default function ProEditor({ rules, credits, onMerged, onSettled }) {
  const [songs, setSongs] = useState([]);
  const [parts, setParts] = useState([]);
  const [options, setOptions] = useState({ outputFormat: "mp3", crossfade: 0 });
  const [link, setLink] = useState("");
  const [addError, setAddError] = useState("");
  const [recorderOpen, setRecorderOpen] = useState(false);
  const [activePart, setActivePart] = useState(null);
  const [consent, setConsent] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [notice, setNotice] = useState("");
  const [player] = useState(() => new EditorPlayer());
  const playback = useSyncExternalStore(player.subscribe, player.getState, player.getState);
  const objectUrls = useRef(new Set());
  const recordings = useRef(0);
  const submitBusy = useRef(false);

  useEffect(() => { player.sync(songs, parts); }, [player, songs, parts]);
  useEffect(() => {
    const urls = objectUrls.current;
    return () => {
      player.dispose();
      urls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [player]);

  const patchSong = (id, patch) => setSongs((current) => patchById(current, id, patch));


  // YouTube songs are prepared on the server; ask until each one is ready.
  const waiting = songs.filter((song) => song.status === "loading" && song.sourceId).map((song) => `${song.id}:${song.sourceId}`).join(",");
  useEffect(() => {
    if (!waiting) return undefined;
    let cancelled = false;
    const timer = setInterval(() => {
      waiting.split(",").forEach(async (pair) => {
        const [id, sourceId] = pair.split(":");
        try {
          const { data } = await getAudioSource(sourceId);
          if (!cancelled) setSongs((current) => patchById(current, Number(id), songFromSource(data)));
        } catch (err) {
          // Keep asking through a network blip; a missing song will never arrive.
          if (!cancelled && err?.response?.status === 404) {
            setSongs((current) => patchById(current, Number(id), { status: "error", error: sourceFailureMessage() }));
          }
        }
      });
    }, POLL_MS);
    return () => { cancelled = true; clearInterval(timer); };
  }, [waiting]);

  const roomForSong = () => {
    if (songs.length < MAX_SONGS) return true;
    setAddError(`You can load up to ${MAX_SONGS} songs. Remove one to add another.`);
    return false;
  };

  const loadLink = async (event) => {
    event.preventDefault();
    const url = link.trim();
    const message = validateLink(url);
    if (message) { setAddError(message); return; }
    if (!roomForSong()) return;
    const id = nextId++;
    setSongs((current) => [...current, { id, kind: "youtube", url, name: "YouTube song", status: "loading", volume: 100, zoom: 1 }]);
    setLink("");
    setAddError("");
    try {
      const { data } = await createAudioSource(url);
      patchSong(id, songFromSource(data));
    } catch (err) {
      patchSong(id, { status: "error", error: mergeError(err) });
    }
  };

  const addFile = async (file, kind) => {
    const message = validateFile(file, rules);
    if (message) { setAddError(message); return; }
    if (!roomForSong()) return;
    const id = nextId++;
    const name = kind === "mic" ? `Recording ${++recordings.current}` : file.name;
    setSongs((current) => [...current, { id, kind, file, name, status: "loading", volume: 100, zoom: 1 }]);
    setAddError("");
    const decoded = await decodeAudioFile(file);
    if (!decoded) { patchSong(id, { status: "error", error: "We couldn't read this file as audio." }); return; }
    const audioUrl = URL.createObjectURL(decoded.preview ?? file);
    objectUrls.current.add(audioUrl);
    patchSong(id, { status: "ready", duration: decoded.duration, peaks: decoded.peaks, audioUrl });
  };

  const removeSong = (id) => {
    setSongs((current) => current.filter((song) => song.id !== id));
    setParts((current) => current.filter((part) => part.songId !== id));
  };

  const canAddPart = parts.length < rules.max_tracks;
  const createPart = (songId, range) => {
    if (!canAddPart) return;
    const id = nextId++;
    setParts((current) => [...current, { id, songId, ...range, fadeIn: 0, fadeOut: 0 }]);
    setActivePart(id);
  };
  const changePart = (id, patch) => {
    setParts((current) => current.map((part) => (part.id === id ? { ...part, ...patch } : part)));
    setActivePart(id);
  };
  const removePart = (id) => setParts((current) => current.filter((part) => part.id !== id));
  const movePart = (id, step) => setParts((current) => {
    const from = current.findIndex((part) => part.id === id);
    const to = from + step;
    if (to < 0 || to >= current.length) return current;
    const next = [...current];
    [next[from], next[to]] = [next[to], next[from]];
    return next;
  });

  const songById = new Map(songs.map((song) => [song.id, song]));
  const numbers = new Map(parts.map((part, index) => [part.id, index + 1]));
  const { partErrors, formError } = validatePro(songs, parts, options, rules);
  const cost = proCost(parts, rules);
  const total = totalSeconds(parts);
  const hasErrors = !!formError || Object.keys(partErrors).length > 0;
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
      const { data: job } = await createAudioMerge(buildProRequest(songs, parts, options));
      onMerged(job);
      setNotice("Your merge has started. It appears under “Your merges” when it's ready.");
    } catch (err) {
      setSubmitError(mergeError(err));
    } finally {
      onSettled();
      submitBusy.current = false;
      setSubmitting(false);
    }
  };

  return (
    <div className="pro">
      <div className="pro-grid">
        <div className="pro-main">
          <section className="pro-card pro-add" aria-labelledby="pro-add-title">
            <h2 id="pro-add-title">Add a song</h2>
            <form className="pro-link" onSubmit={loadLink} noValidate>
              <label className="pro-visually-hidden" htmlFor="pro-link">YouTube link</label>
              <input id="pro-link" type="url" inputMode="url" autoComplete="off" placeholder="Paste a YouTube link"
                value={link} onChange={(event) => setLink(event.target.value)} />
              <button type="submit" className="pro-solid">Load</button>
            </form>
            <div className="pro-add-row">
              <label className="pro-ghost pro-file">
                <Icon><path d="M12 16V4M7 9l5-5 5 5M5 20h14" /></Icon>
                Upload audio
                <input type="file" accept={UPLOAD_EXTENSIONS.join(",")}
                  onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; if (file) addFile(file, "upload"); }} />
              </label>
              <button type="button" className="pro-ghost" onClick={() => setRecorderOpen(true)} disabled={recorderOpen}>
                <Icon><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5.5 11a6.5 6.5 0 0013 0M12 17.5V21" /></Icon>
                Record
              </button>
            </div>
            <p className="pro-sub">
              YouTube videos up to {Math.floor(rules.max_source_seconds / 60)} minutes, files up to {megabytes(rules.max_upload_bytes)}.
              Loading and listening are free; credits are only used when you merge.
            </p>
            {addError && <p className="merger-error" role="alert">{addError}</p>}
          </section>

          {recorderOpen && (
            <Recorder limits={rules} onClose={() => setRecorderOpen(false)}
              onDone={(file) => { setRecorderOpen(false); addFile(file, "mic"); }} />
          )}

          {songs.length === 0 && !recorderOpen && (
            <div className="pro-empty">
              <div className="pro-empty-wave" aria-hidden="true">
                {Array.from({ length: 28 }, (_, i) => <span key={i} style={{ height: `${22 + Math.abs(Math.sin(i * 1.3)) * 70}%` }} />)}
              </div>
              <p>Add your first song to see its waveform here.</p>
            </div>
          )}

          {songs.map((song) => (
            <SongCard key={song.id} song={song} parts={parts.filter((part) => part.songId === song.id)} numbers={numbers}
              limits={rules} player={player} canAdd={canAddPart}
              playing={playback.playing && playback.mode === "song" && playback.songId === song.id}
              onPatch={patchSong} onRemove={removeSong} onCreatePart={createPart} onChangePart={changePart} onSelectPart={setActivePart} />
          ))}
        </div>

        <form className="pro-side" onSubmit={submit} noValidate>
          <section className="pro-card" aria-labelledby="pro-mix-title">
            <h2 id="pro-mix-title">Your mix</h2>
            {parts.length === 0
              ? <p className="pro-sub">Parts you pick appear here, in the order they will play.</p>
              : (
                <ol className="pro-parts">
                  {parts.map((part, index) => (
                    <PartRow key={part.id} part={part} index={index} count={parts.length} song={songById.get(part.songId)}
                      limits={rules} player={player} active={playback.mode === "sequence" ? playback.partId === part.id : activePart === part.id}
                      error={attempted ? partErrors[part.id] : ""} onChange={changePart} onMove={movePart} onRemove={removePart} />
                  ))}
                </ol>
              )}
            {!canAddPart && <p className="pro-sub">You've reached the limit of {rules.max_tracks} parts.</p>}
          </section>

          <section className="pro-card pro-summary" aria-labelledby="pro-summary-title">
            <h2 id="pro-summary-title">Merge</h2>
            <div className="pro-options">
              <label className="pro-time" htmlFor="pro-crossfade">
                <span>Blend between parts</span>
                <select id="pro-crossfade" value={options.crossfade}
                  onChange={(event) => setOptions((current) => ({ ...current, crossfade: Number(event.target.value) }))}>
                  {CROSSFADE_CHOICES.filter((seconds) => seconds <= rules.max_crossfade_seconds).map((seconds) => (
                    <option key={seconds} value={seconds}>{seconds ? `${seconds} second crossfade` : "No blend"}</option>
                  ))}
                </select>
              </label>
              <label className="pro-time" htmlFor="pro-format">
                <span>File type</span>
                <select id="pro-format" value={options.outputFormat}
                  onChange={(event) => setOptions((current) => ({ ...current, outputFormat: event.target.value }))}>
                  {rules.output_formats.map((format) => <option key={format} value={format}>{format.toUpperCase()}</option>)}
                </select>
              </label>
            </div>
            <dl>
              <div><dt>Parts</dt><dd>{parts.length}</dd></div>
              <div><dt>Length</dt><dd>{total ? formatPreciseTime(total) : "—"}</dd></div>
              <div><dt>Cost</dt><dd>{cost == null ? "—" : `${cost} credits`}</dd></div>
            </dl>
            <p className="pro-sub">
              Same price as Simple mode: 1 credit per minute of selected audio, plus {rules.extra_track_credits} per extra part.
              Volume and fades play in the preview; the blend is added in the merged file.
            </p>
            {!affordable && <p className="merger-note">You need {cost} credits. Free credits renew at midnight IST. <SiteLink href="/pricing">See pricing</SiteLink></p>}
            {attempted && formError && <p className="merger-error" role="alert">{formError}</p>}
            <label className="merger-consent">
              <input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} />
              I own this audio or have the right to use it, and I will only use the result as the law and the source's terms allow.
            </label>
            {submitError && <p className="merger-error" role="alert">{submitError}</p>}
            {notice && <p className="merger-success" role="status">{notice}</p>}
            <button type="submit" className="pro-solid pro-merge" disabled={submitting}>
              {submitting ? "Uploading…" : "Merge parts"}
            </button>
          </section>
        </form>
      </div>

      {playback.error && <p className="merger-error pro-player-error" role="alert">{playback.error}</p>}
      {/* Nothing to play until a part is picked, so the floating player stays out of the way. */}
      {parts.length > 0 && <Transport player={player} playing={playback.playing && playback.mode === "sequence"} total={total} />}
    </div>
  );
}
