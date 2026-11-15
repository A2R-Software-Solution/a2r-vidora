import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { formatPreciseTime, formatTime } from "../../utils/formatTime";
import { fitRange, moveEdge, rulerStep, shiftRange } from "../../utils/proMerge";

const RULER_HEIGHT = 24;
const WAVE_HEIGHT = 112;
const BAR = 2;
const SLOT = 4;             // one bar and the gap after it
const DRAG_THRESHOLD = 4;
const EDGE_SCROLL = 28;     // dragging this close to an edge scrolls a zoomed wave
const COLORS = { selected: "#f2652a", idle: "#e7d6c9", tick: "#cdb8a8", label: "#8a7566" };

const inAnyPart = (parts, time) => parts.some((part) => time >= part.start && time < part.end);

// Draws only the visible window of the (possibly zoomed) wave: `offset` pixels
// into a track that is `trackWidth` pixels wide in total.
function draw(canvas, width, song, parts, offset, trackWidth) {
  const ratio = window.devicePixelRatio || 1;
  const height = RULER_HEIGHT + WAVE_HEIGHT;
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const context = canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, width, height);
  const secondsPerPixel = song.duration / trackWidth;
  const from = offset * secondsPerPixel;
  const to = Math.min((offset + width) * secondsPerPixel, song.duration);

  // Time ruler: a label every `step` seconds and four small ticks in between.
  const step = rulerStep(width * secondsPerPixel, width);
  const minor = step / 5;
  const label = step < 1 ? formatPreciseTime : formatTime;
  context.font = "11px Inter, system-ui, sans-serif";
  context.textBaseline = "top";
  for (let i = Math.ceil(from / minor - 1e-6); i * minor <= to + 1e-6; i += 1) {
    const x = Math.round((i * minor) / secondsPerPixel - offset);
    const major = i % 5 === 0;
    context.fillStyle = COLORS.tick;
    context.fillRect(Math.min(x, width - 1), major ? 12 : 17, 1, major ? 10 : 5);
    if (!major) continue;
    const text = label(i * minor);
    const textWidth = context.measureText(text).width;
    context.fillStyle = COLORS.label;
    context.fillText(text, Math.min(Math.max(x - textWidth / 2, 0), width - textWidth), 0);
  }

  // Waveform: one rounded bar per slot of the whole track, orange inside a picked part.
  const peaks = song.peaks;
  const middle = RULER_HEIGHT + WAVE_HEIGHT / 2;
  for (let slot = Math.floor(offset / SLOT); slot * SLOT < offset + width; slot += 1) {
    const time = (slot + 0.5) * SLOT * secondsPerPixel;
    if (time > song.duration) break;
    let peak = 0.18;   // files the browser cannot decode get a flat placeholder
    if (peaks?.length) {
      const first = Math.floor(((slot * SLOT) / trackWidth) * peaks.length);
      const last = Math.max(Math.floor((((slot + 1) * SLOT) / trackWidth) * peaks.length), first + 1);
      peak = 0;
      for (let j = first; j < last && j < peaks.length; j += 1) if (peaks[j] > peak) peak = peaks[j];
    }
    const barHeight = Math.max(peak * (WAVE_HEIGHT - 12), 2);
    context.fillStyle = inAnyPart(parts, time) ? COLORS.selected : COLORS.idle;
    context.beginPath();
    context.roundRect(slot * SLOT - offset, middle - barHeight / 2, BAR, barHeight, 1);
    context.fill();
  }
}

// One song's waveform. Drag across it to pick a part, drag a part to move it,
// drag a part's edge to resize it, click to listen from that point. `snap` is
// the step (in seconds) that dragged edges land on; `zoom` widens the wave so
// fine steps can be placed by eye.
export default function Waveform({ song, parts, numbers, limits, player, canAdd, snap, zoom, onZoom, onCreate, onChange, onSelect }) {
  const scrollerRef = useRef(null);
  const trackRef = useRef(null);
  const canvasRef = useRef(null);
  const playheadRef = useRef(null);
  const drag = useRef(null);
  const center = useRef(0.5);   // the point of the song in the middle of the view, kept when zooming
  const [view, setView] = useState({ width: 0, offset: 0 });
  const [draft, setDraft] = useState(null);
  const maxLength = limits.max_segment_seconds;
  const trackWidth = view.width * zoom;

  useEffect(() => {
    const scroller = scrollerRef.current;
    const observer = new ResizeObserver(([entry]) => {
      setView({ width: Math.floor(entry.contentRect.width), offset: scroller.scrollLeft });
    });
    observer.observe(scroller);
    return () => observer.disconnect();
  }, []);

  // Zooming keeps the middle of the view where it was.
  useLayoutEffect(() => {
    const scroller = scrollerRef.current;
    if (!view.width) return;
    scroller.scrollLeft = Math.max(center.current * view.width * zoom - view.width / 2, 0);
    setView((current) => (current.offset === scroller.scrollLeft ? current : { ...current, offset: scroller.scrollLeft }));
  }, [zoom, view.width]);

  useEffect(() => {
    if (view.width > 0) draw(canvasRef.current, view.width, song, draft ? [...parts, draft] : parts, view.offset, trackWidth);
  }, [view, trackWidth, song, parts, draft]);

  useEffect(() => player.attachPlayhead(song.id, playheadRef.current), [player, song.id]);

  // Ctrl + scroll (also a trackpad pinch) zooms around the pointer; no buttons are shown for it.
  const zoomRef = useRef(onZoom);
  useEffect(() => { zoomRef.current = onZoom; });
  useEffect(() => {
    const scroller = scrollerRef.current;
    let last = 0;
    const onWheel = (event) => {
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      const now = performance.now();
      if (now - last < 120) return;
      last = now;
      const box = trackRef.current.getBoundingClientRect();
      center.current = Math.min(Math.max((event.clientX - box.left) / box.width, 0), 1);
      zoomRef.current(event.deltaY < 0 ? 1 : -1);
    };
    scroller.addEventListener("wheel", onWheel, { passive: false });
    return () => scroller.removeEventListener("wheel", onWheel);
  }, []);

  const scrolled = () => {
    const scroller = scrollerRef.current;
    if (view.width) center.current = (scroller.scrollLeft + view.width / 2) / (view.width * zoom);
    setView((current) => (current.offset === scroller.scrollLeft ? current : { ...current, offset: scroller.scrollLeft }));
  };

  const timeAt = (clientX) => {
    const box = trackRef.current.getBoundingClientRect();
    return Math.min(Math.max((clientX - box.left) / box.width, 0), 1) * song.duration;
  };

  const pointerDown = (event) => {
    if (event.button !== 0) return;
    const target = event.target.closest("[data-role]");
    const part = target ? parts.find((item) => String(item.id) === target.dataset.part) : null;
    drag.current = {
      mode: part ? target.dataset.role : "create", part, x: event.clientX, time: timeAt(event.clientX), moved: false,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const pointerMove = (event) => {
    const state = drag.current;
    if (!state) return;
    if (!state.moved && Math.abs(event.clientX - state.x) < DRAG_THRESHOLD) return;
    state.moved = true;
    if (zoom > 1) {
      const box = scrollerRef.current.getBoundingClientRect();
      if (event.clientX > box.right - EDGE_SCROLL) scrollerRef.current.scrollLeft += 14;
      else if (event.clientX < box.left + EDGE_SCROLL) scrollerRef.current.scrollLeft -= 14;
    }
    const time = timeAt(event.clientX);
    const { mode, part } = state;
    if (mode === "create") {
      if (canAdd) setDraft(fitRange(state.time, time, song.duration, maxLength, time < state.time ? "end" : "start", snap));
    } else if (mode === "move") onChange(part.id, shiftRange(part, time - state.time, song.duration, snap));
    else onChange(part.id, moveEdge(part, mode, time, song.duration, maxLength, snap));
  };

  const pointerUp = (event) => {
    const state = drag.current;
    drag.current = null;
    if (!state) return;
    if (!state.moved) {
      // A plain click: listen from here.
      if (state.part) onSelect(state.part.id);
      player.playSong(song.id, timeAt(event.clientX));
    } else if (state.mode === "create" && draft) onCreate(draft);
    setDraft(null);
  };

  const nudge = (event, part, edge) => {
    const direction = { ArrowLeft: -1, ArrowRight: 1, ArrowDown: -1, ArrowUp: 1 }[event.key];
    if (!direction) return;
    event.preventDefault();
    const amount = direction * snap * (event.shiftKey ? 10 : 1);
    onChange(part.id, moveEdge(part, edge, part[edge] + amount, song.duration, maxLength, snap));
  };

  const place = (range) => ({
    left: `${(range.start / song.duration) * 100}%`,
    width: `${((range.end - range.start) / song.duration) * 100}%`,
  });

  return (
    <div className="wave">
      <div className="wave-scroller" ref={scrollerRef} onScroll={scrolled}>
        <div className="wave-inner" ref={trackRef} style={{ width: `${zoom * 100}%` }} onPointerDown={pointerDown}
          onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={() => { drag.current = null; setDraft(null); }}>
          <canvas ref={canvasRef} className="wave-canvas" style={{ width: view.width, height: RULER_HEIGHT + WAVE_HEIGHT }} aria-hidden="true" />
          <div className="wave-regions" style={{ top: RULER_HEIGHT }}>
            {parts.map((part) => {
              const number = numbers.get(part.id);
              return (
                <div key={part.id} className="wave-region" style={place(part)} data-role="move" data-part={part.id}>
                  <span className="wave-badge">{number}</span>
                  {["start", "end"].map((edge) => (
                    <span key={edge} className={`wave-handle wave-handle-${edge}`} data-role={edge} data-part={part.id}
                      role="slider" tabIndex={0} aria-orientation="horizontal"
                      aria-label={`Part ${number} ${edge}`} aria-valuemin={0} aria-valuemax={Math.floor(song.duration)}
                      aria-valuenow={part[edge]} aria-valuetext={formatPreciseTime(part[edge])}
                      onKeyDown={(event) => nudge(event, part, edge)} />
                  ))}
                </div>
              );
            })}
            {draft && <div className="wave-region wave-region-draft" style={place(draft)} />}
            <div className="wave-playhead" ref={playheadRef} hidden />
          </div>
        </div>
      </div>
      {zoom > 1 && (
        <input className="wave-pan" type="range" min="0" max={Math.max(trackWidth - view.width, 1)} step="1" value={view.offset}
          aria-label={`Scroll the zoomed wave of ${song.name}`}
          onChange={(event) => { scrollerRef.current.scrollLeft = Number(event.target.value); }} />
      )}
    </div>
  );
}
