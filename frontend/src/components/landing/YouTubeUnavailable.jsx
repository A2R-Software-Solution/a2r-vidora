import { useEffect, useState } from "react";
import { config } from "../../config";
import { YOUTUBE_UNAVAILABLE_MESSAGE } from "../../utils/videoInput";
import "./YouTubeUnavailable.css";

const start = () => ({ bird: 48, velocity: 0, pipeX: 100, gapY: 42, score: 0, status: "playing" });

export default function YouTubeUnavailable({ onDismiss, active = true }) {
  const [game, setGame] = useState(start);
  const flap = () => setGame(g => g.status === "playing" ? { ...g, velocity: -2.55 } : g);
  useEffect(() => { if (!active) return; const key = e => { if (e.code === "Space" || e.code === "ArrowUp") { e.preventDefault(); flap(); } }; window.addEventListener("keydown", key); return () => window.removeEventListener("keydown", key); }, [active]);
  useEffect(() => { if (!active || game.status !== "playing") return; const timer = setInterval(() => setGame(g => { const v = g.velocity + .28, bird = g.bird + v; let pipeX = g.pipeX - 1.75, gapY = g.gapY, score = g.score; if (pipeX < -18) { pipeX = 100; gapY = 25 + Math.random() * 48; score++; }
    // Match collision bounds to the visible 8%-wide bird and pipe caps.
    const birdLeft = 19, birdRight = 27, birdTop = bird - 4, birdBottom = bird + 4;
    const pipeLeft = pipeX - 2.3, pipeRight = pipeX + 17.3;
    const overlapsPipe = pipeLeft < birdRight && pipeRight > birdLeft;
    const hit = overlapsPipe && (birdTop < gapY - 14 || birdBottom > gapY + 14);
    return birdTop < 0 || birdBottom > 100 || hit ? { ...g, bird, velocity: v, status: "over" } : { ...g, bird, velocity: v, pipeX, gapY, score }; }), 32); return () => clearInterval(timer); }, [active, game.status]);
  return <section className="youtube-unavailable"><div role="alert"><h2>A little YouTube timeout</h2><p>{YOUTUBE_UNAVAILABLE_MESSAGE}</p></div><a className="outage-report" href={config.bugReportUrl} target="_blank" rel="noopener noreferrer">Report this issue</a><div className="snake-heading"><h3>Play Flappy Bird while you wait</h3><span>Score: {game.score}</span></div><p className="snake-instructions">Click the game or press Space / ↑ to flap.</p><button className="flappy-board" type="button" onClick={flap} aria-label="Flap"><span className="flappy-cloud cloud-a" /><span className="flappy-cloud cloud-b" /><span className="flappy-pipe pipe-top" style={{ left: `${game.pipeX}%`, height: `${game.gapY - 14}%` }} /><span className="flappy-pipe pipe-bottom" style={{ left: `${game.pipeX}%`, top: `${game.gapY + 14}%` }} /><span className="flappy-bird" style={{ top: `${game.bird}%` }}><svg viewBox="0 0 64 64" aria-hidden="true"><ellipse cx="29" cy="33" rx="23" ry="19" fill="#ffd34e" stroke="#9b5420" strokeWidth="3" /><path d="M12 39c9-8 19-6 24 7-10 4-19 1-24-7Z" fill="#ed912c" stroke="#9b5420" strokeWidth="3" strokeLinejoin="round" /><circle cx="39" cy="23" r="8" fill="#fff" stroke="#63381e" strokeWidth="2.5" /><circle cx="41" cy="24" r="3" fill="#29201b" /><path d="M51 30 63 36 51 42Z" fill="#f17827" stroke="#9b5420" strokeWidth="2.5" strokeLinejoin="round" /><path d="M20 19c7-7 18-8 25-2" fill="none" stroke="#fff28a" strokeWidth="3" strokeLinecap="round" opacity=".85" /></svg></span>{game.status === "over" && <span className="snake-overlay">Game over<br /><small>Press Restart to play again</small></span>}</button><div className="snake-actions"><button type="button" onClick={() => setGame(start())}>Restart game</button><button type="button" onClick={onDismiss}>Back to video form</button></div></section>;
}
