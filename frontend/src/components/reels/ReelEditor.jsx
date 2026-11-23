import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  getShort, getShortDownload, getShortDraft, getShortOptions,
  transliterateCaptions,
} from "../../api/videoApi";
import { formatTime } from "../../utils/formatTime";
import {
  DEFAULT_STYLE, MAX_CAPTION_CHARS, MAX_CAPTIONS, PREVIEW_FONTS, PREVIEW_FONTS_URL, activeCaptionIndex,
  autoSync, captionErrors, captionsForRequest, cleanText, frameSize, hasDevanagari, hexToRgba, karaokeWords, previewScale,
} from "../../utils/reelEditor";
import { shortError } from "../../utils/shorts";
import { loadYouTubeApi } from "../../utils/youtubeApi";
import "./ReelEditor.css";

const TABS = [["caption", "Caption", "text"], ["font", "Font", "font"], ["style", "Style", "palette"],
  ["position", "Position", "position"], ["background", "Background", "image"]];
const BACKGROUNDS = { blur: "Blurred video", fill: "Crop to fill", solid: "Solid colour" };
const SWATCHES = ["#FFFFFF", "#FFE600", "#000000", "#2F6BFF", "#8B3DFF", "#FF3DA8"];
const PRESET_ICONS = { clean: "sparkle", bold: "font", karaoke: "wave", minimal: "lines", pop: "sparkle" };

const ICONS = {
  text: "M5 6V4h14v2M12 4v16M9 20h6",
  font: "M4 19l5-14 5 14M6 14h6M16 9h4m-2-2v6",
  palette: "M12 3a9 9 0 100 18c1.5 0 2-1 1.5-2s0-2 1.5-2h2a3 3 0 003-3c0-6-4-11-8-11z",
  position: "M12 8a4 4 0 100 8 4 4 0 000-8zM12 2v3M12 19v3M2 12h3M19 12h3",
  image: "M4 5h16v14H4zM4 16l5-5 4 4 3-3 4 4M9 9.5h.01",
  sparkle: "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z",
  wave: "M4 12h1m3-4v8m4-11v14m4-11v8m4-3h1",
  lines: "M5 7h14M5 12h14M5 17h9",
  play: "M8 5v14l11-7z",
  pause: "M8 5v14M16 5v14",
  trash: "M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v6M14 11v6",
  plus: "M12 5v14M5 12h14",
  back: "M19 12H5m6-6l-6 6 6 6",
  volume: "M4 9v6h4l5 4V5L8 9zM16 9a4 4 0 010 6",
  mute: "M4 9v6h4l5 4V5L8 9zM17 9l4 6m0-6l-4 6",
  download: "M12 4v11m0 0l-4-4m4 4l4-4M5 20h14",
};

function Icon({ name, filled }) {
  return <svg className="re-icon" viewBox="0 0 24 24" aria-hidden="true" fill={filled ? "currentColor" : "none"}
    stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d={ICONS[name]} /></svg>;
}

function usePreviewFonts() {
  useEffect(() => {
    if (document.querySelector(`link[href="${PREVIEW_FONTS_URL}"]`)) return;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = PREVIEW_FONTS_URL;
    document.head.appendChild(link);
  }, []);
}

function Switch({ checked, onChange, label }) {
  return <button type="button" role="switch" aria-checked={checked} aria-label={label} className="re-switch"
    onClick={() => onChange(!checked)}><span /></button>;
}

function ColorField({ label, value, onChange }) {
  return <label className="re-color"><span>{label}</span>
    <input type="color" value={value} onChange={(event) => onChange(event.target.value.toUpperCase())} />
    <code>{value}</code></label>;
}

function Slider({ label, value, min, max, unit = "", onChange }) {
  return <label className="re-slider"><span>{label}</span>
    <div><input type="range" min={min} max={max} value={value} onChange={(event) => onChange(Number(event.target.value))} />
      <output>{value}{unit && ` ${unit}`}</output></div></label>;
}

function CaptionOverlay({ caption, style, time, scale }) {
  if (!caption) return null;
  const font = PREVIEW_FONTS[style.font] || PREVIEW_FONTS.poppins_semibold;
  const text = style.uppercase ? caption.text.toUpperCase() : caption.text;
  const placement = style.position === "top" ? { top: "8%" } : style.position === "middle" ?
    { top: "50%", transform: "translateY(-50%)" } : { bottom: "8%" };
  const words = style.highlight ? karaokeWords(text, caption.start, caption.end, time) : null;
  return <div className="re-caption-wrap" style={placement}>
    <span className="re-caption" style={{
      fontFamily: `"${font.family}", sans-serif`, fontWeight: font.weight, fontSize: `${style.size * scale}px`,
      color: style.color,
      WebkitTextStroke: style.outline && !style.box ? `${style.outline_width * scale * 2}px ${style.outline_color}` : undefined,
      paintOrder: "stroke fill",
      background: style.box ? hexToRgba(style.box_color, style.box_opacity) : undefined,
    }}>
      {words ? words.map((item, index) => <span key={index} style={{ color: item.lit ? style.highlight_color : style.color }}>
        {item.word}{index < words.length - 1 ? " " : ""}</span>) : text}
    </span>
  </div>;
}

// Same fields as the preset, so a preset reads as "selected" while the style matches it.
const sameStyle = (style, preset, defaults) => {
  const target = { ...DEFAULT_STYLE, ...defaults, ...preset };
  return Object.keys(preset).every((key) => style[key] === target[key]);
};

export default function ReelEditor({ videoId, youtubeId, clip, creditCost, credits, onClose, onRender }) {
  const duration = clip.end_time - clip.start_time;
  usePreviewFonts();
  const [options, setOptions] = useState(null);
  const [captions, setCaptions] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [style, setStyle] = useState({ ...DEFAULT_STYLE });
  const [ratio, setRatio] = useState("9:16");
  const [background, setBackground] = useState("blur");
  const [backgroundColor, setBackgroundColor] = useState("#000000");
  const [tab, setTab] = useState("caption");
  const [leftView, setLeftView] = useState("preview");
  const [autoSyncOn, setAutoSyncOn] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [job, setJob] = useState(null);
  const [downloading, setDownloading] = useState(false);
  const [hinglishBackup, setHinglishBackup] = useState(null);
  const [converting, setConverting] = useState(false);
  const [convertError, setConvertError] = useState("");
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [ready, setReady] = useState(false);
  const [frame, setFrame] = useState({ width: 270, height: 480 });
  const [top, setTop] = useState(72);
  const playerRef = useRef(null);
  const playerHost = useRef(null);
  const frameRef = useRef(null);
  const backRef = useRef(null);
  const submitRef = useRef(false);

  const loaded = !!options && !!captions;
  const set = (patch) => setStyle((current) => ({ ...current, ...patch }));
  const { width: outputWidth, height: outputHeight } = frameSize(ratio, options);

  // The editor sits under the site's navbar, like the rest of the pages.
  useEffect(() => {
    const measure = () => setTop(Math.round(document.querySelector(".site-navbar")?.getBoundingClientRect().bottom || 72));
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  // Server lists (fonts, ratios, presets) and the transcript captions to edit.
  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try {
        const [{ data: offered }, { data: draft }] = await Promise.all([
          getShortOptions(controller.signal), getShortDraft(videoId, clip, controller.signal)]);
        if (controller.signal.aborted) return;
        setOptions(offered);
        setStyle({ ...DEFAULT_STYLE, ...offered.defaults });
        setCaptions(draft.captions);
      } catch (err) {
        if (!controller.signal.aborted) setLoadError(shortError(err));
      }
    })();
    return () => controller.abort();
  }, [videoId, clip]);

  useEffect(() => { backRef.current?.focus(); }, []);
  useEffect(() => {
    const onKey = (event) => { if (event.key === "Escape" && !submitRef.current) onClose(); };
    document.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = previous; };
  }, [onClose]);

  // The preview is the YouTube player, restricted to the clip, under a caption overlay.
  useEffect(() => {
    if (!youtubeId || !loaded || !playerHost.current) return undefined;
    let cancelled = false;
    let player;
    loadYouTubeApi().then((YT) => {
      if (cancelled || !playerHost.current) return;
      const target = document.createElement("div");
      playerHost.current.appendChild(target);
      player = new YT.Player(target, {
        videoId: youtubeId,
        playerVars: { start: clip.start_time, end: clip.end_time, controls: 0, rel: 0, modestbranding: 1,
          playsinline: 1, disablekb: 1, fs: 0, iv_load_policy: 3 },
        events: {
          onReady: () => { if (!cancelled) { playerRef.current = player; setReady(true); } },
          onStateChange: (event) => {
            if (cancelled) return;
            setPlaying(event.data === YT.PlayerState.PLAYING);
            // `end` stops the first pass; loop the clip instead.
            if (event.data === YT.PlayerState.ENDED) { player.seekTo(clip.start_time, true); player.playVideo(); }
          },
        },
      });
    });
    return () => {
      cancelled = true;
      playerRef.current = null;
      setReady(false);
      try { player?.destroy?.(); } catch { /* the iframe is already gone */ }
    };
  }, [youtubeId, loaded, clip.start_time, clip.end_time]);

  useEffect(() => {
    if (!ready) return undefined;
    const timer = setInterval(() => {
      const player = playerRef.current;
      if (!player?.getCurrentTime) return;
      const relative = player.getCurrentTime() - clip.start_time;
      if (relative >= duration - 0.05) { player.seekTo(clip.start_time, true); return; }
      setTime(Math.max(0, relative));
    }, 100);
    return () => clearInterval(timer);
  }, [ready, clip.start_time, duration]);

  useEffect(() => {
    const element = frameRef.current;
    if (!element || typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width && height) setFrame({ width, height });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [ratio, leftView, loaded]);

  const togglePlay = () => {
    const player = playerRef.current;
    if (!player) return;
    if (playing) player.pauseVideo(); else player.playVideo();
  };
  const toggleMute = () => {
    const player = playerRef.current;
    if (!player) return;
    if (muted) player.unMute(); else player.mute();
    setMuted(!muted);
  };
  const seek = (seconds, play = false) => {
    setTime(seconds);
    playerRef.current?.seekTo(clip.start_time + seconds, true);
    if (play) playerRef.current?.playVideo();
  };

  const errors = useMemo(() => (captions ? captionErrors(captions, duration) : []), [captions, duration]);
  const activeIndex = captions ? activeCaptionIndex(captions, time) : -1;
  const scale = previewScale(frame.width, frame.height);
  const affordable = credits == null || credits.available >= creditCost;
  const pending = job?.status === "queued" || job?.status === "rendering";
  // Once a reel is rendering or done, its settings are frozen until "Make another version".
  const locked = !!job && job.status !== "failed" && job.status !== "expired";
  const canRender = !!captions && !!options && errors.length === 0 && affordable && !submitting && !pending && job?.status !== "completed";

  // With Auto Sync on, every change to the lines re-times them over the clip.
  const changeCaptions = (change) => setCaptions((current) => {
    const next = change(current);
    return autoSyncOn ? autoSync(next, duration) : next;
  });
  const updateCaption = (index, patch) => changeCaptions((current) => current.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  const addCaption = () => changeCaptions((current) => {
    const last = current[current.length - 1];
    const start = Math.min(last ? last.end : 0, Math.max(0, duration - 0.5));
    return [...current, { start: Number(start.toFixed(2)), end: Number(Math.min(duration, start + 2).toFixed(2)), text: "New caption" }];
  });
  const removeCaption = (index) => changeCaptions((current) => current.filter((_, i) => i !== index));
  const toggleAutoSync = (on) => {
    setAutoSyncOn(on);
    if (on) setCaptions((current) => autoSync(current, duration));
  };

  // The reel stays here while it renders; the download appears when it is ready.
  useEffect(() => {
    if (!job || (job.status !== "queued" && job.status !== "rendering")) return undefined;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const { data } = await getShort(videoId, job.id, controller.signal);
        if (!controller.signal.aborted) setJob(data);
      } catch {
        // Keep the last known state and ask again shortly.
        if (!controller.signal.aborted) setJob((current) => (current ? { ...current } : current));
      }
    }, 4000);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [job, videoId]);

  const downloadReel = async () => {
    if (downloading || !job) return;
    setDownloading(true);
    setSubmitError("");
    try {
      const { data } = await getShortDownload(videoId, job.id, true);
      const link = document.createElement("a");
      link.href = data.url;
      link.rel = "noopener";
      link.download = "vidora-short.mp4";
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      setSubmitError(shortError(err));
    } finally {
      setDownloading(false);
    }
  };

  const convertHinglish = async () => {
    if (converting) return;
    setConverting(true);
    setConvertError("");
    try {
      const { data } = await transliterateCaptions(captions.map((caption) => caption.text));
      setHinglishBackup(captions);
      setCaptions(captions.map((caption, index) => ({ ...caption, text: cleanText(data.texts[index]) || caption.text })));
    } catch (err) {
      setConvertError(shortError(err));
    } finally {
      setConverting(false);
    }
  };
  const undoHinglish = () => { setCaptions(hinglishBackup); setHinglishBackup(null); };

  const applyPreset = (preset) => setStyle({ ...DEFAULT_STYLE, ...options.defaults, ...preset.style });
  const activePreset = options && options.presets.find((preset) => sameStyle(style, preset.style, options.defaults))?.key;

  const render = useCallback(async () => {
    if (submitRef.current || !canRender) return;
    submitRef.current = true;
    setSubmitting(true);
    setSubmitError("");
    try {
      const created = await onRender({ ratio, background, background_color: backgroundColor, style, captions: captionsForRequest(captions) });
      if (created) setJob(created);
    } catch (err) {
      setSubmitError(shortError(err));
    } finally {
      submitRef.current = false;
      setSubmitting(false);
    }
  }, [canRender, onRender, ratio, background, backgroundColor, style, captions]);

  const thumbnail = youtubeId ? `https://i.ytimg.com/vi/${youtubeId}/hqdefault.jpg` : "";

  return <div className="re-page" role="dialog" aria-modal="true" aria-labelledby="re-title" style={{ top }}>
    {loadError ? <div className="re-state" role="alert"><p>{loadError}</p>
      <button type="button" className="re-back" ref={backRef} onClick={onClose}><Icon name="back" /> Back</button></div> :
      !loaded ? <div className="re-state" role="status"><p>Loading the editor…</p></div> :
      <>
        <div className="re-grid">
          <aside className="re-card re-left" aria-label="Preview">
            <div className="re-left-head">
              <div className="re-seg" role="tablist" aria-label="Left panel">
                <button type="button" role="tab" aria-selected={leftView === "preview"} onClick={() => setLeftView("preview")}>Preview</button>
                <button type="button" role="tab" aria-selected={leftView === "captions"} onClick={() => setLeftView("captions")}>Captions ({captions.length})</button>
              </div>
              <select className="re-ratio" value={ratio} onChange={(event) => setRatio(event.target.value)} aria-label="Video ratio" disabled={locked}>
                {options.ratios.map((item) => <option key={item.key} value={item.key}>{item.key}</option>)}
              </select>
            </div>
            <div className="re-stage" hidden={leftView !== "preview"}>
              <div className={`re-frame re-frame--${background}`} ref={frameRef} style={{ "--ar": outputWidth / outputHeight, aspectRatio: `${outputWidth} / ${outputHeight}`,
                backgroundColor: background === "solid" ? backgroundColor : "#120d0a" }}>
                {background === "blur" && thumbnail && <div className="re-blur" style={{ backgroundImage: `url(${thumbnail})` }} />}
                <div className="re-video"><div ref={playerHost} className="re-yt" /></div>
                <CaptionOverlay caption={activeIndex >= 0 ? captions[activeIndex] : null} style={style} time={time} scale={scale} />
              </div>
              <div className="re-transport">
                <button type="button" onClick={togglePlay} disabled={!ready} aria-label={playing ? "Pause" : "Play"}><Icon name={playing ? "pause" : "play"} filled={!playing} /></button>
                <span>{formatTime(time)} / {formatTime(duration)}</span>
                <button type="button" className="re-mute" onClick={toggleMute} disabled={!ready} aria-label={muted ? "Unmute" : "Mute"}><Icon name={muted ? "mute" : "volume"} /></button>
                <input type="range" min="0" max={duration} step="0.1" value={Math.min(time, duration)} disabled={!ready}
                  onChange={(event) => seek(Number(event.target.value))} aria-label="Position in the clip" />
              </div>
              <p className="re-note">The preview is close to the final video; fonts and timing may differ slightly.</p>
            </div>
            {leftView === "captions" && <ol className="re-transcript">
              {captions.map((caption, index) => <li key={index}>
                <button type="button" className={index === activeIndex ? "is-active" : ""} onClick={() => { setLeftView("preview"); seek(caption.start, true); }}>
                  <b>{formatTime(caption.start)}</b> {caption.text}</button></li>)}
            </ol>}
          </aside>

          <section className={`re-card re-right${locked ? " is-locked" : ""}`} aria-label="Caption controls" inert={locked}>
            <div className="re-right-head">
              <div><h2 id="re-title">Customize Your Reel</h2>
                <p>Style your captions, edit text, choose ratio and background.</p></div>
            </div>
            {locked && <p className="re-locked" role="status">These settings are locked for the reel you created. Click “Make another version” to change them.</p>}

            <div className="re-presets">
              <h3>Style Presets</h3>
              <div className="re-preset-row">
                {options.presets.map((preset) => <button type="button" key={preset.key} className="re-preset" aria-pressed={activePreset === preset.key}
                  onClick={() => applyPreset(preset)}><Icon name={PRESET_ICONS[preset.key] || "sparkle"} />{preset.label}</button>)}
              </div>
            </div>

            <div className="re-tabs" role="tablist" aria-label="Caption settings">
              {TABS.map(([key, label, icon]) => <button type="button" role="tab" key={key} aria-selected={tab === key} onClick={() => setTab(key)}>
                <Icon name={icon} />{label}</button>)}
            </div>

            <div className="re-tabpanel" role="tabpanel">
              {tab === "caption" && <div className="re-caption-tab">
                <div className="re-edit">
                  <div className="re-edit-head"><h3>Edit Captions</h3>
                    <div className="re-edit-tools">
                      {hinglishBackup ? <button type="button" className="re-chip" onClick={undoHinglish}>देवनागरी</button> :
                        captions.some((caption) => hasDevanagari(caption.text)) && <button type="button" className="re-chip" onClick={convertHinglish} disabled={converting}>
                          {converting ? "Converting…" : "Hinglish"}</button>}
                      <label className="re-autosync">Auto Sync <Switch checked={autoSyncOn} onChange={toggleAutoSync} label="Auto Sync" /></label></div></div>
                  {convertError && <p className="re-error" role="alert">{convertError}</p>}
                  <ol className="re-lines">
                    {captions.map((caption, index) => <li key={index} className={index === activeIndex ? "is-active" : ""}>
                      <button type="button" className="re-line-play" onClick={() => seek(caption.start, true)} aria-label={`Play line ${index + 1}`}><Icon name="play" filled /></button>
                      {autoSyncOn ? <span className="re-line-time">{formatTime(caption.start)} – {formatTime(caption.end)}</span> :
                        <span className="re-line-times">
                          <input type="number" min="0" max={duration} step="0.1" value={caption.start} aria-label={`Line ${index + 1} start (seconds)`}
                            onChange={(event) => updateCaption(index, { start: Number(event.target.value) })} />
                          <i>–</i>
                          <input type="number" min="0" max={duration} step="0.1" value={caption.end} aria-label={`Line ${index + 1} end (seconds)`}
                            onChange={(event) => updateCaption(index, { end: Number(event.target.value) })} /></span>}
                      <input type="text" className="re-line-text" value={caption.text} maxLength={MAX_CAPTION_CHARS} aria-label={`Line ${index + 1} text`}
                        onChange={(event) => updateCaption(index, { text: event.target.value })} onFocus={() => seek(caption.start)} />
                      <button type="button" className="re-icon-btn" onClick={() => removeCaption(index)} aria-label={`Delete line ${index + 1}`}><Icon name="trash" /></button>
                    </li>)}
                  </ol>
                  <button type="button" className="re-outline re-add" onClick={addCaption} disabled={captions.length >= MAX_CAPTIONS}><Icon name="plus" /> Add Caption</button>
                  {errors.length > 0 && <ul className="re-errors" role="alert">{errors.slice(0, 4).map((message) => <li key={message}>{message}</li>)}</ul>}
                </div>
                <div className="re-quick">
                  <label className="re-field"><span>Font</span>
                    <select value={style.font} onChange={(event) => set({ font: event.target.value })}
                      style={{ fontFamily: `"${(PREVIEW_FONTS[style.font] || PREVIEW_FONTS.poppins_semibold).family}", sans-serif` }}>
                      {options.fonts.map((font) => <option key={font.key} value={font.key}>{font.label}</option>)}</select></label>
                  <Slider label="Size" value={style.size} min={options.limits.size[0]} max={options.limits.size[1]} unit="px" onChange={(size) => set({ size })} />
                  <div className="re-field"><span>Color</span>
                    <div className="re-swatches">
                      {SWATCHES.map((color) => <button type="button" key={color} className="re-swatch" style={{ background: color }} aria-label={`Text colour ${color}`}
                        aria-pressed={style.color.toUpperCase() === color} onClick={() => set({ color })} />)}
                      <input type="color" className="re-swatch-custom" value={style.color} aria-label="Custom text colour" onChange={(event) => set({ color: event.target.value.toUpperCase() })} />
                    </div></div>
                  <div className="re-inline"><span>Outline</span><Switch checked={style.outline} onChange={(outline) => set({ outline })} label="Outline" />
                    {style.outline && <><input type="color" className="re-box" value={style.outline_color} aria-label="Outline colour" onChange={(event) => set({ outline_color: event.target.value.toUpperCase() })} />
                      <select value={style.outline_width} aria-label="Outline width" onChange={(event) => set({ outline_width: Number(event.target.value) })}>
                        {Array.from({ length: 8 }, (_, i) => i + 1).map((n) => <option key={n} value={n}>{n} px</option>)}</select></>}</div>
                  <div className="re-inline"><span>Background Box</span><Switch checked={style.box} onChange={(box) => set({ box })} label="Background box" />
                    {style.box && <input type="color" className="re-box" value={style.box_color} aria-label="Box colour" onChange={(event) => set({ box_color: event.target.value.toUpperCase() })} />}</div>
                  {style.box && <Slider label="Box opacity" value={style.box_opacity} min={0} max={100} unit="%" onChange={(box_opacity) => set({ box_opacity })} />}
                </div>
              </div>}

              {tab === "font" && <>
                <div className="re-fonts">
                  {options.fonts.map((font) => {
                    const face = PREVIEW_FONTS[font.key] || PREVIEW_FONTS.poppins_semibold;
                    return <button type="button" key={font.key} aria-pressed={style.font === font.key} className="re-font"
                      style={{ fontFamily: `"${face.family}", sans-serif`, fontWeight: face.weight }} onClick={() => set({ font: font.key })}>
                      {font.label}</button>;
                  })}
                </div>
                <Slider label="Size" value={style.size} min={options.limits.size[0]} max={options.limits.size[1]} unit="px" onChange={(size) => set({ size })} />
                <div className="re-inline"><span>UPPERCASE</span><Switch checked={style.uppercase} onChange={(uppercase) => set({ uppercase })} label="Uppercase" /></div>
              </>}

              {tab === "style" && <>
                <ColorField label="Text colour" value={style.color} onChange={(color) => set({ color })} />
                <div className="re-inline"><span>Outline</span><Switch checked={style.outline} onChange={(outline) => set({ outline })} label="Outline" /></div>
                {style.outline && <>
                  <ColorField label="Outline colour" value={style.outline_color} onChange={(outline_color) => set({ outline_color })} />
                  <Slider label="Outline width" value={style.outline_width} min={options.limits.outline_width[0]} max={options.limits.outline_width[1]} unit="px" onChange={(outline_width) => set({ outline_width })} />
                </>}
                <div className="re-inline"><span>Background box</span><Switch checked={style.box} onChange={(box) => set({ box })} label="Background box" /></div>
                {style.box && <>
                  <ColorField label="Box colour" value={style.box_color} onChange={(box_color) => set({ box_color })} />
                  <Slider label="Box opacity" value={style.box_opacity} min={0} max={100} unit="%" onChange={(box_opacity) => set({ box_opacity })} />
                </>}
                <div className="re-inline"><span>Karaoke highlight</span><Switch checked={style.highlight} onChange={(highlight) => set({ highlight })} label="Karaoke highlight" /></div>
                {style.highlight && <ColorField label="Highlight colour" value={style.highlight_color} onChange={(highlight_color) => set({ highlight_color })} />}
              </>}

              {tab === "position" && <div className="re-choices">
                {options.positions.map((position) => <button type="button" key={position} aria-pressed={style.position === position}
                  onClick={() => set({ position })}>{position[0].toUpperCase() + position.slice(1)}</button>)}
              </div>}

              {tab === "background" && <>
                <div className="re-choices">
                  {options.backgrounds.map((key) => <button type="button" key={key} aria-pressed={background === key}
                    onClick={() => setBackground(key)}>{BACKGROUNDS[key] || key}</button>)}
                </div>
                {background === "solid" && <ColorField label="Background colour" value={backgroundColor} onChange={setBackgroundColor} />}
                <p className="re-note">Blurred video fills the empty space around the picture; crop to fill trims the picture to the frame.</p>
              </>}
            </div>
          </section>
        </div>

        <div className="re-bottom">
          <button type="button" className="re-back" ref={backRef} onClick={onClose} disabled={submitting}><Icon name="back" /> {job ? "Back to ideas" : "Back"}</button>
          <p role="status">
            {pending ? "Creating your reel with captions… this takes a minute or two. Stay on this page: the download button appears here when it is ready." :
              job?.status === "completed" ? "Your reel is ready. Download it, or go back to find more ideas." :
              job?.status === "failed" ? "Creation failed and its credits were returned. You can try again." :
              job?.status === "expired" ? "This reel has expired. Create it again." :
              !affordable ? `You need ${creditCost} credits to create this reel.` :
              `Creating the reel uses ${creditCost} credits${credits ? ` · You have ${credits.available}` : ""}.`}
            {submitError && <span className="re-error" role="alert"> {submitError}</span>}
          </p>
          {job?.status === "completed" ? <>
            <button type="button" className="re-outline" onClick={() => setJob(null)}>Make another version</button>
            <button type="button" className="re-primary" onClick={downloadReel} disabled={downloading}>
              <Icon name="download" />{downloading ? "Preparing…" : "Download MP4"}</button>
          </> : <button type="button" className="re-primary" onClick={render} disabled={!canRender}>
            <Icon name="sparkle" filled />{submitting ? "Submitting…" : pending ? "Creating…" : "Create Reel (Final Render)"}
          </button>}
        </div>
      </>}
  </div>;
}
