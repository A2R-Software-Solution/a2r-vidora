import { formatTime } from "../../utils/formatTime";

export default function TimestampChip({ startSeconds, endSeconds, onClick }) {
  if (!Number.isFinite(startSeconds) || startSeconds < 0) return null;
  return (
    <button type="button" className="timestamp" onClick={() => onClick?.(startSeconds)}
      aria-label={`Play source at ${formatTime(startSeconds)}`}>
      ▶ {formatTime(startSeconds)}{Number.isFinite(endSeconds) ? ` – ${formatTime(endSeconds)}` : ""}
    </button>
  );
}
