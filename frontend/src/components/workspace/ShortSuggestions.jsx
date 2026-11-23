import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { createShort, getShortDownload, listShorts, suggestShorts } from "../../api/videoApi";
import { formatTime } from "../../utils/formatTime";
import { clipKey, isShortExpired, isShortPending, shortCards, shortError } from "../../utils/shorts";
import { extractYouTubeId } from "../../utils/youtube";
import { SHORT_CREDIT_COST } from "../../utils/pricing";
import { refreshCredits, useCredits } from "../../hooks/useCredits";
import SiteLink from "../common/SiteLink";
import { requireSignIn } from "../../utils/authGate";
import "./ShortSuggestions.css";

// The editor (preview player, fonts, controls) loads only when it is opened.
const ReelEditor = lazy(() => import("../reels/ReelEditor"));

function FeaturedShort({ clip, videoId, active, onSeek, onCreate, onCustomize, creating, canCreate }) {
  const job = clip.job;
  const [preview, setPreview] = useState("");
  const [action, setAction] = useState("");
  const [error, setError] = useState("");
  const videoRef = useRef(null);
  const actionRef = useRef(false);
  const expired = job && isShortExpired(job);
  const pending = job && isShortPending(job);
  const completed = job?.status === "completed" && !expired;

  useEffect(() => {
    if (!active) videoRef.current?.pause();
  }, [active]);

  const openMedia = async (download) => {
    if (actionRef.current) return;
    actionRef.current = true;
    setAction(download ? "download" : "preview");
    setError("");
    try {
      // Fetch a fresh signed URL for every action.
      const { data } = await getShortDownload(videoId, job.id, download);
      if (download) {
        const link = document.createElement("a");
        link.href = data.url;
        link.rel = "noopener";
        link.download = "vidora-short.mp4";
        document.body.appendChild(link);
        link.click();
        link.remove();
      } else setPreview(data.url);
    } catch (err) {
      setError(shortError(err));
    } finally {
      actionRef.current = false;
      setAction("");
    }
  };

  const status = expired ? "Expired" : pending ? (job.status === "queued" ? "Queued — your reel will start shortly. It will be ready to download here." : "Creating your reel with captions… this takes a minute or two. Download it here when it's ready.") :
    completed ? "Your reel is ready — download it below." : job?.status === "failed" ?
      "Creation failed and its credits were returned. You can retry." : "";

  return <article className="short-featured">
    <span className="short-chip">{job ? "Your Short" : "Short idea"}</span>
    <h3>{clip.title}</h3>
    {clip.hook && <p className="short-hook">“{clip.hook.replace(/^["“]|["”]$/g, "")}”</p>}
    <button type="button" className="short-time" onClick={() => onSeek(clip.start_time)}
      aria-label={`Play original video at ${formatTime(clip.start_time)}`}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
      {formatTime(clip.start_time)} – {formatTime(clip.end_time)} · {clip.end_time - clip.start_time}s
    </button>
    {clip.reason && <p className="short-reason">{clip.reason}</p>}
    {status && <p className="short-status" role="status">{status}</p>}
    {job && <p className="short-expiry">{expired ? "Expired" : "Available until"} {new Date(job.expires_at).toLocaleString()}</p>}
    <div className="short-actions">
      <button type="button" className="short-btn" disabled={!!action}
        onClick={() => (completed ? openMedia(false) : onSeek(clip.start_time))}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z" /></svg>{action === "preview" ? "Loading…" : "Preview"}
      </button>
      {completed && <button type="button" className="short-btn short-btn--primary" onClick={() => openMedia(true)} disabled={!!action}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11m0 0l-4-4m4 4l4-4M5 20h14" /></svg>{action === "download" ? "Preparing…" : "Download MP4"}
      </button>}
      {!pending && !expired && <button type="button" className={`short-btn${completed ? "" : " short-btn--primary"}`} onClick={() => onCustomize(clip)} disabled={creating}>
        Customize <span aria-hidden="true">→</span>
      </button>}
      {!expired && (!job || job.status === "failed") && <button type="button" className="short-btn short-btn--solid" onClick={() => onCreate(clip)}
        disabled={!canCreate || creating}>
        {creating ? "Submitting…" : job ? "Retry" : "Create Reel"}
      </button>}
    </div>
    {preview && completed && <video ref={videoRef} className="short-preview" src={preview} controls playsInline preload="metadata"
      aria-label={`Preview of ${clip.title}`} onError={() => {
        setPreview("");
        setError("The preview link may have expired. Click Preview to load a fresh link.");
      }} />}
    {error && <p className="shorts-error" role="alert">{error}</p>}
  </article>;
}

function Thumb({ clip, youtubeId, isNew, onSelect }) {
  const job = clip.job;
  return <button type="button" className="short-thumb" onClick={() => onSelect(clip)}
    title={clip.title} style={youtubeId ? { backgroundImage: `url(https://i.ytimg.com/vi/${youtubeId}/mqdefault.jpg)` } : undefined}>
    {isNew && <span className="short-thumb-new">New</span>}
    <span className="short-thumb-time">{formatTime(clip.start_time)}</span>
    {job && <span className="short-thumb-flag">{isShortPending(job) ? "Creating" : job.status === "completed" ? "Ready" : ""}</span>}
    <span className="short-thumb-title">{clip.title}</span>
  </button>;
}

export default function ShortSuggestions({ videoId, youtubeUrl, onSeek, active = true }) {
  // Every idea found so far, and how many times "Find reel ideas" was pressed.
  const [ideas, setIdeas] = useState([]);
  const [batches, setBatches] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [historyError, setHistoryError] = useState("");
  const [history, setHistory] = useState(null);
  const [creating, setCreating] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [selectedKey, setSelectedKey] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [editing, setEditing] = useState(null);
  const createBusy = useRef(false);
  const suggestionBusy = useRef(false);
  const wasPending = useRef(false);
  const credits = useCredits();
  const creditCost = history?.credit_cost ?? SHORT_CREDIT_COST;
  const youtubeId = extractYouTubeId(youtubeUrl);

  useEffect(() => {
    if (!active) return undefined;
    const controller = new AbortController();
    let timer;
    const poll = async () => {
      let delay = 30000;
      try {
        const { data } = await listShorts(videoId, controller.signal);
        if (controller.signal.aborted) return;
        setHistory(data);
        setHistoryError("");
        const pending = data.items.some(isShortPending);
        // A finished render settles its credits; a failed one returns them.
        if (wasPending.current && !pending) void refreshCredits();
        wasPending.current = pending;
        if (pending) delay = 5000;
      } catch (err) {
        if (controller.signal.aborted) return;
        setHistoryError(shortError(err));
      }
      if (!controller.signal.aborted) timer = setTimeout(poll, delay);
    };
    poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [videoId, active, refresh]);

  const generate = async () => {
    if (suggestionBusy.current || !requireSignIn()) return;
    suggestionBusy.current = true;
    setLoading(true);
    setError("");
    try {
      const { data } = await suggestShorts(videoId);
      const batch = batches + 1;
      setIdeas((previous) => [...previous, ...data.filter((idea) => !previous.some((known) => clipKey(known) === clipKey(idea))).map((idea) => ({ ...idea, batch }))]);
      setBatches(batch);
    } catch (err) {
      setError(shortError(err));
    } finally {
      suggestionBusy.current = false;
      setLoading(false);
    }
  };

  // Throws, so the editor can show why a render was refused.
  const submit = async (clip, options) => {
    if (createBusy.current) throw new Error("busy");
    if (!requireSignIn()) throw new Error("Sign in to create a reel.");
    createBusy.current = true;
    setCreating(clipKey(clip));
    setError("");
    try {
      const { data: job } = await createShort(videoId, clip, options);
      setHistory((previous) => {
        const items = [...(previous?.items || []).filter((item) => item.id !== job.id), job];
        return { ...previous, items, used: items.filter((item) => item.status !== "failed").length };
      });
      // The finished reel shows in the main card, not among the other ideas.
      setSelectedKey(clipKey(clip));
      return job;
    } finally {
      // Reconcile a lost response: the server may have accepted the job.
      setRefresh((value) => value + 1);
      void refreshCredits();
      createBusy.current = false;
      setCreating("");
    }
  };

  const create = async (clip) => {
    try { await submit(clip); } catch (err) {
      if (err?.message !== "busy") setError(shortError(err));
    }
  };

  const cards = shortCards(ideas, history?.items || []);
  const ideaKeys = new Set(ideas.map(clipKey));
  const ideaCards = cards.filter((clip) => ideaKeys.has(clipKey(clip)));
  const earlier = cards.filter((clip) => !ideaKeys.has(clipKey(clip)));
  const selected = cards.find((clip) => clipKey(clip) === selectedKey) || ideaCards[0] || earlier[0];
  // Other ideas appear only after "Find reel ideas" was pressed again.
  const more = batches >= 2 ? ideaCards.filter((clip) => clip !== selected) : [];
  // An unknown balance never blocks creating; the server answers 402 if short.
  const affordable = credits == null || credits.available >= creditCost;
  const canCreate = !!history && !historyError && affordable && !creating;
  return <section className="short-suggestions" aria-labelledby="shorts-heading">
    <div className="shorts-heading">
      <div><h2 id="shorts-heading"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M13 3l1.8 5.2L20 10l-5.2 1.8L13 17l-1.8-5.2L6 10l5.2-1.8zM5 16l.9 2.1L8 19l-2.1.9L5 22l-.9-2.1L2 19l2.1-.9z" /></svg>Create your reel</h2>
        <p>Find two standout moments, then choose a clip to turn into a reel.</p></div>
      <button type="button" className="short-find" onClick={generate} disabled={loading}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20L16 8m0 0l1-4 1 4 4 1-4 1-1 4-1-4z" /></svg>{loading ? "Finding ideas…" : "Find reel ideas"}
      </button>
    </div>
    <p className="short-allowance" role="status">
      Each reel uses {creditCost} credits{credits ? ` · You have ${credits.available}` : ""}
    </p>
    {!affordable && <p className="shorts-note">
      You need {creditCost} credits to create a reel.{" "}
      <SiteLink href="/pricing">See pricing</SiteLink>
    </p>}
    {historyError && <div className="shorts-error" role="alert">{historyError} <button type="button" className="short-refresh" onClick={() => setRefresh((value) => value + 1)}>Refresh status</button></div>}
    {error && <p className="shorts-error" role="alert">{error}</p>}
    {selected && <FeaturedShort key={`${videoId}-${clipKey(selected)}-${selected.job?.id || "idea"}-${selected.job?.status || ""}`} clip={selected} videoId={videoId}
      active={active} onSeek={onSeek} onCreate={create} onCustomize={setEditing}
      creating={creating === clipKey(selected)} canCreate={canCreate} />}
    {more.length > 0 && <div className="short-more">
      <div className="short-more-head">
        <h3>More Suggestions</h3>
        {more.length > 3 && <button type="button" onClick={() => setShowAll((value) => !value)}>{showAll ? "Show less" : "View all →"}</button>}
      </div>
      <div className={`short-thumbs${showAll ? " is-all" : ""}`}>
        {more.map((clip) => <Thumb key={clipKey(clip)} clip={clip} youtubeId={youtubeId} isNew={clip.batch === batches}
          onSelect={(picked) => { setSelectedKey(clipKey(picked)); onSeek(picked.start_time); }} />)}
      </div>
    </div>}
    {editing && <Suspense fallback={<p className="shorts-note" role="status">Loading the editor…</p>}>
      <ReelEditor videoId={videoId} youtubeId={youtubeId} clip={editing} creditCost={creditCost} credits={credits}
        onClose={() => setEditing(null)} onRender={(options) => submit(editing, options)} />
    </Suspense>}
  </section>;
}
