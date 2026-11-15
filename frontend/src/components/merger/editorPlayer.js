// Preview playback for the Song Merger Pro editor. It plays each song's own
// audio in the browser: a single song from any point, or the whole mix (every
// part in order, with its volume and fades). The moving playheads and the
// transport clock are written straight to the DOM so React does not re-render
// on every frame. Blends between parts exist only in the merged file.
import { formatTime } from "../../utils/formatTime";
import { locateInSequence, previewGain, secondsBefore } from "../../utils/proMerge";

const IDLE = { playing: false, mode: null, songId: null, partId: null, error: "" };
const PREVIEW_ERROR = "We couldn't play this song's preview. Remove it and add it again.";

export class EditorPlayer {
  constructor() {
    this.songs = [];
    this.parts = [];
    this.audios = new Map();     // song id -> { audio, url }
    this.playheads = new Map();  // song id -> element
    this.transport = null;       // { time, range }
    this.listeners = new Set();
    this.state = IDLE;
    this.frame = 0;
  }

  subscribe = (listener) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getState = () => this.state;

  set(patch) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((listener) => listener());
  }

  // Called after every edit, so playback follows the parts as they change.
  sync(songs, parts) {
    this.songs = songs;
    this.parts = parts;
    const alive = new Set(songs.map((song) => song.id));
    for (const [id, entry] of this.audios) {
      if (!alive.has(id)) {
        this.release(entry.audio);
        this.audios.delete(id);
      }
    }
    const { mode, songId, partId } = this.state;
    if (mode && (!alive.has(songId) || (mode === "sequence" && !parts.some((part) => part.id === partId)))) this.stop();
  }

  release(audio) {
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
  }

  audioFor(song) {
    let entry = this.audios.get(song.id);
    if (!entry) {
      const audio = new Audio();
      audio.preload = "auto";
      audio.addEventListener("error", () => { if (audio.getAttribute("src")) this.fail(song.id); });
      entry = { audio, url: null };
      this.audios.set(song.id, entry);
    }
    if (entry.url !== song.audioUrl) {
      entry.url = song.audioUrl;
      entry.audio.src = song.audioUrl;
    }
    return entry.audio;
  }

  fail(songId) {
    if (this.state.songId !== songId) return;
    this.stop();
    this.set({ error: PREVIEW_ERROR });
  }

  start(mode, song, part, at) {
    const current = this.audios.get(this.state.songId)?.audio;
    const audio = this.audioFor(song);
    if (current && current !== audio) current.pause();
    try {
      audio.currentTime = at;
    } catch {
      // Not seekable yet: it plays from wherever it is.
    }
    audio.volume = part ? previewGain(part, song.volume, at) : Math.min(song.volume / 100, 1);
    this.set({ playing: true, mode, songId: song.id, partId: part?.id ?? null, error: "" });
    audio.play().catch((error) => { if (error?.name !== "AbortError") this.fail(song.id); });
    cancelAnimationFrame(this.frame);
    this.frame = requestAnimationFrame(this.tick);
  }

  startPart(part, at) {
    const song = this.songs.find((item) => item.id === part.songId);
    if (!song || song.status !== "ready") return this.stop();
    return this.start("sequence", song, part, at);
  }

  tick = () => {
    const { playing, mode, songId, partId } = this.state;
    if (!playing) return;
    const song = this.songs.find((item) => item.id === songId);
    const audio = this.audios.get(songId)?.audio;
    if (!song || !audio) { this.stop(); return; }
    const at = audio.currentTime;
    if (mode === "sequence") {
      const index = this.parts.findIndex((part) => part.id === partId);
      if (index < 0) { this.stop(); return; }
      const part = this.parts[index];
      if (at >= part.end || audio.ended) {
        const next = this.parts[index + 1];
        if (next) this.startPart(next, next.start);
        else this.stop();
        return;
      }
      audio.volume = previewGain(part, song.volume, at);
      this.paint(song, at, secondsBefore(this.parts, index) + Math.max(at - part.start, 0));
    } else {
      if (audio.ended) { this.stop(); return; }
      audio.volume = Math.min(song.volume / 100, 1);
      this.paint(song, at, null);
    }
    this.frame = requestAnimationFrame(this.tick);
  };

  paint(song, at, mixSeconds) {
    for (const [id, element] of this.playheads) {
      element.hidden = id !== song.id;
      if (id !== song.id) continue;
      element.style.left = `${Math.min(at / (song.duration || 1), 1) * 100}%`;
      // A zoomed wave scrolls along so the playhead stays in view.
      const scroller = element.closest(".wave-scroller");
      if (scroller && scroller.scrollWidth > scroller.clientWidth + 1) {
        const x = element.offsetLeft;
        if (x < scroller.scrollLeft || x > scroller.scrollLeft + scroller.clientWidth - 24) scroller.scrollLeft = Math.max(x - 24, 0);
      }
    }
    if (mixSeconds != null) this.paintTransport(mixSeconds);
  }

  paintTransport(seconds) {
    if (!this.transport) return;
    const { time, range } = this.transport;
    time.textContent = formatTime(seconds);
    range.style.setProperty("--fill", `${Math.min(seconds / (Number(range.max) || 1), 1) * 100}%`);
    // Leave the slider alone while the user is dragging it.
    if (!range.matches(":active")) range.value = String(seconds);
  }

  playSequence(index = 0, offset = 0) {
    const part = this.parts[index];
    if (part) this.startPart(part, part.start + offset);
  }

  playSong(songId, at = 0) {
    const song = this.songs.find((item) => item.id === songId);
    if (song?.status === "ready") this.start("song", song, null, Math.min(Math.max(at, 0), song.duration || 0));
  }

  pause() {
    this.audios.get(this.state.songId)?.audio.pause();
    cancelAnimationFrame(this.frame);
    this.set({ playing: false });
  }

  resume() {
    const audio = this.audios.get(this.state.songId)?.audio;
    if (!audio) { this.stop(); return; }
    const songId = this.state.songId;
    this.set({ playing: true, error: "" });
    audio.play().catch((error) => { if (error?.name !== "AbortError") this.fail(songId); });
    cancelAnimationFrame(this.frame);
    this.frame = requestAnimationFrame(this.tick);
  }

  // The transport's main button: play, pause or resume the whole mix.
  toggle() {
    if (this.state.playing) this.pause();
    else if (this.state.mode === "sequence") this.resume();
    else this.playSequence(0);
  }

  // A song card's own button: listen to that song alone.
  toggleSong(songId) {
    const { playing, mode, songId: current } = this.state;
    if (mode === "song" && current === songId) {
      if (playing) this.pause();
      else this.resume();
    } else this.playSong(songId, 0);
  }

  // Jumps to the previous or next part of the mix.
  step(delta) {
    const index = this.state.mode === "sequence" ? this.parts.findIndex((part) => part.id === this.state.partId) : -1;
    if (index < 0) { this.playSequence(0); return; }
    this.playSequence(Math.min(Math.max(index + delta, 0), this.parts.length - 1));
  }

  seekSequence(seconds) {
    const { index, offset } = locateInSequence(this.parts, seconds);
    this.playSequence(index, offset);
  }

  stop() {
    this.audios.get(this.state.songId)?.audio.pause();
    cancelAnimationFrame(this.frame);
    for (const element of this.playheads.values()) element.hidden = true;
    this.paintTransport(0);
    if (this.state !== IDLE) this.set({ ...IDLE });
  }

  attachPlayhead(songId, element) {
    this.playheads.set(songId, element);
    return () => { if (this.playheads.get(songId) === element) this.playheads.delete(songId); };
  }

  attachTransport(transport) {
    this.transport = transport;
    return () => { if (this.transport === transport) this.transport = null; };
  }

  dispose() {
    this.stop();
    for (const entry of this.audios.values()) this.release(entry.audio);
    this.audios.clear();
  }
}
