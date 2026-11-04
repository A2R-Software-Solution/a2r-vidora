import { useEffect, useId, useRef, useState } from "react";
import SiteLink from "../components/common/SiteLink";
import { createDownload, getDownloadFile, getDownloadLimits, listDownloads, previewDownload } from "../api/mediaDownloadApi";
import { refreshCredits, useCredits } from "../hooks/useCredits";
import { formatTime } from "../utils/formatTime";
import {
  OWNERSHIP_TEXT, RIGHTS_WARNING, downloadCost, downloadError, downloadFailureMessage, groupQualities,
  isDownloadActive,
} from "../utils/mediaDownload";
import "./DownloaderPage.css";

const POLL_MS = 4000;

function QualityGroup({ title, qualities, options, selected, onSelect, name }) {
  return (
    <fieldset className="dl-qualities">
      <legend>{title}</legend>
      {qualities.map((quality) => {
        const cost = downloadCost(options, quality.code);
        const available = quality.available !== false;
        return (
          <label key={quality.code} className={`dl-quality${available ? "" : " dl-quality--off"}`}>
            <input type="radio" name={name} value={quality.code} checked={selected === quality.code}
              onChange={() => onSelect(quality.code)} disabled={!available} />
            <span className="dl-quality-label">{quality.label}</span>
            <span className="dl-quality-cost">
              {!available ? "Coming soon" : cost == null ? "—" : `${cost} credit${cost === 1 ? "" : "s"}`}
            </span>
          </label>
        );
      })}
    </fieldset>
  );
}

function JobCard({ job }) {
  const [busy, setBusy] = useState(false);
  const open = async () => {
    setBusy(true);
    try {
      const { data } = await getDownloadFile(job.id);
      window.location.assign(data.url);
    } catch (err) {
      alert(downloadError(err));
    } finally {
      setBusy(false);
    }
  };
  const label = isDownloadActive(job) ? "Preparing…" : job.status === "completed" ? "Ready" : job.status === "expired" ? "Expired" : "Failed";
  return (
    <li className="dl-job">
      <div className="dl-job-head">
        <h3>{job.title || "Untitled media"}</h3>
        <span className={`dl-status dl-status--${job.status}`}>{label}</span>
      </div>
      <p className="dl-hint">
        {job.quality.replace("_", " ").toUpperCase()} · {formatTime(job.duration_seconds)} · {job.credit_cost} credits
      </p>
      {job.status === "failed" && <p className="dl-error" role="alert">{downloadFailureMessage(job)}</p>}
      {job.status === "completed" && (
        <button type="button" className="dl-primary dl-open" onClick={open} disabled={busy}>
          {busy ? "Preparing link…" : "Download file"}
        </button>
      )}
    </li>
  );
}

export default function DownloaderPage({ signedIn }) {
  const credits = useCredits();
  const [limits, setLimits] = useState(null);
  const [url, setUrl] = useState("");
  const [preview, setPreview] = useState(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const [quality, setQuality] = useState("");
  const [consent, setConsent] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [notice, setNotice] = useState("");
  const [jobs, setJobs] = useState(null);
  const [historyError, setHistoryError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const submitBusy = useRef(false);
  const uid = useId();

  useEffect(() => {
    const controller = new AbortController();
    getDownloadLimits(controller.signal).then(({ data }) => setLimits(data)).catch(() => setLimits({ enabled: false, qualities: [] }));
    return () => controller.abort();
  }, []);

  // No history until the backend says the feature is on (an older API has no /downloads).
  const enabled = limits?.enabled === true;
  // While the limits load, the form and history are drawn (inactive) so the page
  // keeps its final height instead of growing and pushing the footer down.
  const loading = limits === null;
  useEffect(() => {
    if (!enabled) return undefined;
    const controller = new AbortController();
    listDownloads(controller.signal)
      .then(({ data }) => { setJobs(data.items); setHistoryError(""); })
      .catch((err) => { if (err?.code !== "ERR_CANCELED") setHistoryError(downloadError(err)); });
    return () => controller.abort();
  }, [enabled, refresh, signedIn]);

  // Keep the list fresh while any download is still being prepared.
  const anyActive = (jobs || []).some(isDownloadActive);
  useEffect(() => {
    if (!anyActive) return undefined;
    const timer = window.setTimeout(() => setRefresh((value) => value + 1), POLL_MS);
    return () => window.clearTimeout(timer);
  }, [anyActive, jobs]);

  const groups = groupQualities(limits?.qualities);
  const cost = downloadCost(preview?.options, quality);
  const available = preview?.wallet?.available ?? 0;
  const affordable = cost != null && cost <= available;
  const canSubmit = !!preview && !!quality && consent && affordable && !submitting;

  const check = async (event) => {
    event.preventDefault();
    if (loading || !url.trim()) return;
    setPreviewBusy(true);
    setPreviewError("");
    setSubmitError("");
    setNotice("");
    setConsent(false);
    setQuality("");
    try {
      const { data } = await previewDownload(url.trim());
      setPreview(data);
    } catch (err) {
      setPreview(null);
      setPreviewError(downloadError(err));
    } finally {
      setPreviewBusy(false);
    }
  };

  const submit = async (event) => {
    event.preventDefault();
    if (!canSubmit || submitBusy.current) return;
    submitBusy.current = true;
    setSubmitting(true);
    setSubmitError("");
    try {
      const { data: job } = await createDownload({ url: preview.url, quality });
      setJobs((previous) => [job, ...(previous || []).filter((item) => item.id !== job.id)]);
      setNotice("Your download has started. It appears below when it's ready.");
      setConsent(false);
    } catch (err) {
      setSubmitError(downloadError(err));
    } finally {
      // Reconcile a lost response: the server may have accepted the job.
      setRefresh((value) => value + 1);
      void refreshCredits();
      submitBusy.current = false;
      setSubmitting(false);
    }
  };

  return (
    <article className="public-page dl-page">
      <header className="public-header">
        <p className="public-eyebrow">Media Downloader</p>
        <h1>Download audio or video from your own YouTube content.</h1>
        <p className="public-intro">
          Paste a YouTube link, pick a quality, and download the file. Each quality has its own credit price.
        </p>
        {enabled && credits?.available != null ? (
          <p className="dl-balance" role="status">
            Credits left: <strong>{credits.available}</strong>
            {credits.purchased_balance > 0 && <> (including {credits.purchased_balance} purchased)</>}
          </p>
        ) : (loading || enabled) && (
          // Hold the pill's space until the balance arrives, so the page doesn't jump.
          <p className="dl-balance balance-pending" aria-hidden="true">&nbsp;</p>
        )}
      </header>

      <p className="dl-warning" role="note"><strong>Your content only.</strong> {RIGHTS_WARNING}</p>

      {!loading && !enabled ? (
        <p className="dl-note" role="status">The Media Downloader is launching soon. Please check back shortly.</p>
      ) : (
        <>
          <form className="dl-check" onSubmit={check} noValidate>
            <div className="dl-field">
              <label htmlFor={`${uid}-url`}>YouTube link</label>
              <input id={`${uid}-url`} type="url" inputMode="url" autoComplete="off"
                placeholder="https://www.youtube.com/watch?v=…" value={url}
                onChange={(event) => setUrl(event.target.value)} aria-invalid={!!previewError} />
            </div>
            <button type="submit" className="dl-primary" disabled={loading || previewBusy || !url.trim()}>
              {previewBusy ? "Checking…" : "Check link"}
            </button>
          </form>
          {previewError && <p className="dl-error" role="alert">{previewError}</p>}

          {preview && (
            <section className="dl-preview" aria-labelledby={`${uid}-preview`}>
              <div className="dl-preview-media">
                {preview.thumbnail && <img src={preview.thumbnail} alt="" width="160" height="90" />}
                <div>
                  <h2 id={`${uid}-preview`}>{preview.title || "Untitled video"}</h2>
                  <p className="dl-hint">Length {formatTime(preview.duration_seconds)}</p>
                </div>
              </div>

              <QualityGroup title="Audio" qualities={groups.audio} options={preview.options}
                selected={quality} onSelect={setQuality} name={`${uid}-quality`} />
              <QualityGroup title="Video" qualities={groups.video} options={preview.options}
                selected={quality} onSelect={setQuality} name={`${uid}-quality`} />

              {quality && !affordable && (
                <p className="dl-note" role="status">
                  This needs {cost} credits and you have {available}. Free credits renew at midnight IST.{" "}
                  <SiteLink href="/pricing">See pricing</SiteLink>
                </p>
              )}

              <label className="dl-consent">
                <input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} />
                {OWNERSHIP_TEXT}
              </label>
              {!consent && quality && <p className="dl-hint">Tick the box above to enable the download.</p>}
              {submitError && <p className="dl-error" role="alert">{submitError}</p>}
              {notice && <p className="dl-success" role="status">{notice}</p>}
              <button type="button" className="dl-primary dl-submit" disabled={!canSubmit} onClick={submit}>
                {submitting ? "Starting…" : cost != null ? `Download for ${cost} credits` : "Download"}
              </button>
            </section>
          )}
        </>
      )}

      {(loading || enabled) && <section className="dl-history" aria-labelledby={`${uid}-history`}>
        <h2 id={`${uid}-history`}>Your downloads</h2>
        {historyError && <p className="dl-error" role="alert">{historyError}</p>}
        {jobs === null && !historyError && <p className="dl-hint">Loading your downloads…</p>}
        {jobs && jobs.length === 0 && !historyError && (
          <p className="dl-hint">Nothing here yet. Finished files stay available for a limited time.</p>
        )}
        {jobs && jobs.length > 0 && <ul className="dl-jobs">{jobs.map((job) => <JobCard key={job.id} job={job} />)}</ul>}
      </section>}
    </article>
  );
}
