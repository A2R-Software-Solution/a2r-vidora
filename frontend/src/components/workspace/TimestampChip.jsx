import { formatTime } from "../../utils/formatTime";

export default function TimestampChip({ startSeconds, endSeconds, onClick }) {
  return (
    <button className="timestamp" onClick={() => onClick?.(startSeconds)}>
      ▶ {formatTime(startSeconds)} – {formatTime(endSeconds)}
    </button>
  );
}