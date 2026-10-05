import { useEffect, useRef, useState } from "react";
import { createShort, getShortDownload, listShorts, suggestShorts } from "../../api/videoApi";
import { formatTime } from "../../utils/formatTime";
import { clipKey, isShortExpired, isShortPending, shortCards, shortError } from "../../utils/shorts";

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
          "Creation failed. You can retry; this attempt doesn't use a free slot." : "Vertical video · captions · 720p"}
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
        if (data.items.some(isShortPending)) delay = 5000;
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
        return { items, free_limit: previous?.free_limit ?? 2, used: items.filter((item) => item.status !== "failed").length };
      });
    } catch (err) {
      setError(shortError(err));
    } finally {
      // Reconcile a lost response: the server may have accepted the job.
      setRefresh((value) => value + 1);
      createBusy.current = false;
      setCreating("");
    }
  };

  const cards = shortCards(suggestions, history?.items || []);
  const canCreate = !!history && !historyError && history.used < history.free_limit && !creating;
  return <section className="short-suggestions" aria-labelledby="shorts-heading">
    <div className="shorts-heading">
      <div><h2 id="shorts-heading">Create Shorts</h2><p>Find two standout moments, then choose which videos to create.</p></div>
      <button type="button" onClick={generate} disabled={loading}>{loading ? "Finding ideas…" : "Suggest Shorts"}</button>
    </div>
    <p className="short-allowance" role="status">{history ? `${history.used}/${history.free_limit} free Shorts used for this video` : "Checking your free Shorts allowance…"}</p>
    {history && history.used >= history.free_limit && <p className="shorts-note">Your free slots are used or reserved by videos in progress.</p>}
    {historyError && <div className="shorts-error" role="alert">{historyError} <button type="button" className="short-refresh" onClick={() => setRefresh((value) => value + 1)}>Refresh status</button></div>}
    {error && <p className="shorts-error" role="alert">{error}</p>}
    {cards.length > 0 && <div className="shorts-list">
      {cards.map((clip) => <ShortCard key={`${videoId}-${clipKey(clip)}-${clip.job?.status || "idea"}`} clip={clip} videoId={videoId}
        active={active} onSeek={onSeek} onCreate={create} creating={creating === clipKey(clip)} canCreate={canCreate} />)}
    </div>}
  </section>;
}
