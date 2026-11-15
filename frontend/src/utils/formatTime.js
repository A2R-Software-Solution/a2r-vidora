export function formatTime(totalSeconds) {
  if (totalSeconds == null || isNaN(totalSeconds)) return "00:00";

  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = Math.floor(totalSeconds % 60);

  const pad = (n) => String(n).padStart(2, "0");

  if (hours > 0) {
    return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
  }
  return `${pad(minutes)}:${pad(seconds)}`;
}

// Like formatTime, but keeps fractions of a second when there are any:
// 83.45 -> "01:23.45", 83 -> "01:23". Exact to a millisecond.
export function formatPreciseTime(totalSeconds) {
  if (totalSeconds == null || isNaN(totalSeconds)) return "00:00";
  const millis = Math.round(totalSeconds * 1000);
  const fraction = millis % 1000;
  const whole = formatTime(Math.floor(millis / 1000));
  return fraction ? `${whole}.${String(fraction).padStart(3, "0").replace(/0+$/, "")}` : whole;
}
