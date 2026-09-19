import { useEffect, useReducer, useRef } from "react";
import { config } from "../../config";
import { YOUTUBE_UNAVAILABLE_MESSAGE } from "../../utils/videoInput";
import { BOARD_SIZE, newGame, snakeReducer } from "../../utils/snake";
import "./YouTubeUnavailable.css";

const KEYS = { ArrowUp: "up", w: "up", ArrowDown: "down", s: "down",
  ArrowLeft: "left", a: "left", ArrowRight: "right", d: "right" };

export default function YouTubeUnavailable({ onDismiss }) {
  const [game, dispatch] = useReducer(snakeReducer, undefined, newGame);
  const boardRef = useRef(null);

  useEffect(() => { boardRef.current?.focus({ preventScroll: true }); }, []);
  useEffect(() => {
    if (game.status !== "playing") return;
    const timer = setInterval(() => dispatch({ type: "tick", random: Math.random() }), 260);
    return () => clearInterval(timer);
  }, [game.status]);
  useEffect(() => {
    const pauseWhenHidden = () => {
      if (document.hidden && game.status === "playing") dispatch({ type: "pause" });
    };
    document.addEventListener("visibilitychange", pauseWhenHidden);
    return () => document.removeEventListener("visibilitychange", pauseWhenHidden);
  }, [game.status]);

  const turn = direction => {
    dispatch({ type: "direction", direction });
    boardRef.current?.focus({ preventScroll: true });
  };

  return (
    <section className="youtube-unavailable" aria-label="YouTube temporarily unavailable">
      <div role="alert">
        <h2>A little YouTube timeout</h2>
        <p>{YOUTUBE_UNAVAILABLE_MESSAGE}</p>
      </div>
      <a className="outage-report" href={config.bugReportUrl} target="_blank" rel="noopener noreferrer">
        Report this issue ?
      </a>
      <div className="snake-heading"><h3>Play Snake while you wait</h3><span>Score: {game.score}</span></div>
      <p className="snake-instructions" id="snake-instructions">Use arrow keys, WASD, or the buttons below. Space pauses.</p>
      <div className="snake-board" ref={boardRef} tabIndex={0} role="group" aria-label="Snake game"
        aria-describedby="snake-instructions" onKeyDown={event => {
          const direction = KEYS[event.key] || KEYS[event.key.toLowerCase()];
          if (direction) { event.preventDefault(); turn(direction); }
          if (event.code === "Space") { event.preventDefault(); dispatch({ type: "pause" }); }
        }}>
        {game.snake.map((cell, index) => <span key={`${cell.x}-${cell.y}`} aria-hidden="true"
          className={`snake-cell ${index === 0 ? "snake-head" : ""}`}
          style={{ left: `${cell.x * 100 / BOARD_SIZE}%`, top: `${cell.y * 100 / BOARD_SIZE}%` }} />)}
        <span className="snake-food" aria-hidden="true"
          style={{ left: `${game.food.x * 100 / BOARD_SIZE}%`, top: `${game.food.y * 100 / BOARD_SIZE}%` }} />
        {game.status !== "playing" && <div className="snake-overlay" role="status">
          {game.status === "paused" ? "Paused" : game.status === "won" ? "You won!" : "Game over"}
        </div>}
      </div>
      <div className="snake-controls" aria-label="Game controls">
        <button type="button" aria-label="Move left" onClick={() => turn("left")}>?</button>
        <button type="button" aria-label="Move up" onClick={() => turn("up")}>?</button>
        <button type="button" aria-label="Move down" onClick={() => turn("down")}>?</button>
        <button type="button" aria-label="Move right" onClick={() => turn("right")}>?</button>
      </div>
      <div className="snake-actions">
        {["playing", "paused"].includes(game.status) && <button type="button" onClick={() => dispatch({ type: "pause" })}>
          {game.status === "paused" ? "Resume game" : "Pause game"}
        </button>}
        <button type="button" onClick={() => { dispatch({ type: "restart" }); boardRef.current?.focus(); }}>Restart game</button>
        <button type="button" onClick={onDismiss}>Back to video form</button>
      </div>
      <p className="snake-note">No automatic retries. You can come back and try your video later.</p>
    </section>
  );
}
