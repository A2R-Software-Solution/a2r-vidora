import { useEffect, useRef, useState } from "react";
import { createShort, getShortDownload, listShorts, suggestShorts } from "../../api/videoApi";
import { formatTime } from "../../utils/formatTime";
import { clipKey, isShortExpired, isShortPending, shortCards, shortError } from "../../utils/shorts";
import { SHORT_CREDIT_COST } from "../../utils/pricing";
import { refreshCredits, useCredits } from "../../hooks/useCredits";
import SiteLink from "../common/SiteLink";

function ShortCard({ clip, videoId, active, onSeek, onCreate, creating, canCreate }) {
  const job = clip.job;
  const [preview, setPreview] = useState("");
  const [action, setAction] = useState("");
  const [error, setError] = useState("");
  const videoRef = useRef(null);
  const actionRef = useRef(false);
  const expired = job && isShortExpired(job);
  const pending = job && isShortPending(job);

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

  return <article className="short-card">
    <span>{job ? "YOUR SHORT" : "SHORT IDEA"}</span>
    <h3>{clip.title}</h3>
    {clip.hook && <p className="short-hook">{clip.hook}</p>}
    <button type="button" className="short-time" onClick={() => onSeek(clip.start_time)}
      aria-label={`Play original video at ${formatTime(clip.start_time)}`}>
      {formatTime(clip.start_time)} – {formatTime(clip.end_time)} · {clip.end_time - clip.start_time}s
    </button>
    {clip.reason && <p>{clip.reason}</p>}
    <div className="short-status" role="status">
      {expired ? "Expired" : pending ? (job.status === "queued" ? "Queued — waiting to start" : "Creating your video with captions…") :
        job?.status === "completed" ? "Ready to download" : job?.status === "failed" ?
          "Creation failed and its credits were returned. You can retry." : "Vertical video · captions · 720p"}
    </div>
    {job && <p className="short-expiry">{expired ? "Expired" : "Available until"} {new Date(job.expires_at).toLocaleString()}</p>}
    <div className="short-actions">
      {!expired && (!job || job.status === "failed") && <button type="button" onClick={() => onCreate(clip)}
        disabled={!canCreate || creating}>
        {creating ? "Submitting…" : job ? "Retry creation" : "Create Short"}
      </button>}
      {!expired && job?.status === "completed" && <>
        <button type="button" onClick={() => openMedia(false)} disabled={!!action}>{action === "preview" ? "Loading…" : "Preview"}</button>
        <button type="button" onClick={() => openMedia(true)} disabled={!!action}>{action === "download" ? "Preparing…" : "Download MP4"}</button>
      </>}
    </div>
    {preview && !expired && <video ref={videoRef} className="short-preview" src={preview} controls playsInline preload="metadata"
      aria-label={`Preview of ${clip.title}`} onError={() => {
        setPreview("");
        setError("The preview link may have expired. Click Preview to load a fresh link.");
      }} />}
    {error && <p className="shorts-error" role="alert">{error}</p>}
  </article>;
}

export default function ShortSuggestions({ videoId, onSeek, active = true }) {
  const [suggestions, setSuggestions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [historyError, setHistoryError] = useState("");
  const [history, setHistory] = useState(null);
  const [creating, setCreating] = useState("");
  const [refresh, setRefresh] = useState(0);
  const createBusy = useRef(false);
  const suggestionBusy = useRef(false);
  const wasPending = useRef(false);
  const credits = useCredits();
  const creditCost = history?.credit_cost ?? SHORT_CREDIT_COST;

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
    if (suggestionBusy.current) return;
    suggestionBusy.current = true;
    setLoading(true);
    setError("");
    try {
      const { data } = await suggestShorts(videoId);
      setSuggestions(data);
    } catch (err) {
      setError(shortError(err));
    } finally {
      suggestionBusy.current = false;
      setLoading(false);
    }
  };

  const create = async (clip) => {
    if (createBusy.current) return;
    createBusy.current = true;
    setCreating(clipKey(clip));
    setError("");
    try {
      const { data: job } = await createShort(videoId, clip);
      setHistory((previous) => {
        const items = [...(previous?.items || []).filter((item) => item.id !== job.id), job];
        return { ...previous, items, used: items.filter((item) => item.status !== "failed").length };
      });
    } catch (err) {
      setError(shortError(err));
    } finally {
      // Reconcile a lost response: the server may have accepted the job.
      setRefresh((value) => value + 1);
      void refreshCredits();
      createBusy.current = false;
      setCreating("");
    }
  };

  const cards = shortCards(suggestions, history?.items || []);
  // An unknown balance never blocks creating; the server answers 402 if short.
  const affordable = credits == null || credits.available >= creditCost;
  const canCreate = !!history && !historyError && affordable && !creating;
  return <section className="short-suggestions" aria-labelledby="shorts-heading">
    <div className="shorts-heading">
      <div><h2 id="shorts-heading">Create your reel</h2><p>Find two standout moments, then choose a clip to turn into a reel.</p></div>
      <button type="button" onClick={generate} disabled={loading}>{loading ? "Finding ideas…" : "Find reel ideas"}</button>
    </div>
    <p className="short-allowance" role="status">
      Each Short uses {creditCost} credits{credits ? ` · You have ${credits.available}` : ""}
    </p>
    {!affordable && <p className="shorts-note">
      You need {creditCost} credits to create a Short. Free credits renew at midnight IST.{" "}
      <SiteLink href="/pricing">See pricing</SiteLink>
    </p>}
    {historyError && <div className="shorts-error" role="alert">{historyError} <button type="button" className="short-refresh" onClick={() => setRefresh((value) => value + 1)}>Refresh status</button></div>}
    {error && <p className="shorts-error" role="alert">{error}</p>}
    {cards.length > 0 && <div className="shorts-list">
      {cards.map((clip) => <ShortCard key={`${videoId}-${clipKey(clip)}-${clip.job?.status || "idea"}`} clip={clip} videoId={videoId}
        active={active} onSeek={onSeek} onCreate={create} creating={creating === clipKey(clip)} canCreate={canCreate} />)}
    </div>}
  </section>;
}
