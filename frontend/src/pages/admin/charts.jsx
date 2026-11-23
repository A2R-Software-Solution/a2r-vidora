import { useId, useState } from "react";

// Smooth line through the points (horizontal-tangent curves, so it never overshoots).
function curve(points) {
  if (points.length < 2) return points.length ? `M${points[0][0]},${points[0][1]}` : "";
  let d = `M${points[0][0]},${points[0][1]}`;
  for (let i = 1; i < points.length; i += 1) {
    const [x0, y0] = points[i - 1];
    const [x1, y1] = points[i];
    const mid = (x0 + x1) / 2;
    d += ` C${mid},${y0} ${mid},${y1} ${x1},${y1}`;
  }
  return d;
}

// A rounded axis maximum: 1, 2, 5 or 10 times a power of ten.
function niceMax(value) {
  if (value <= 0) return 4;
  const power = 10 ** Math.floor(Math.log10(value));
  const fraction = value / power;
  return (fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10) * power;
}

export function Sparkline({ values, color }) {
  const id = useId();
  const width = 200;
  const height = 50;
  const top = Math.max(...values, 1);
  const step = values.length > 1 ? width / (values.length - 1) : width;
  const points = values.map((value, i) => [i * step, height - 4 - (value / top) * (height - 10)]);
  const line = curve(points);
  return <svg className="ad-spark" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
    <defs><linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stopColor={color} stopOpacity=".28" /><stop offset="100%" stopColor={color} stopOpacity="0" />
    </linearGradient></defs>
    {line && <path d={`${line} L${width},${height} L0,${height} Z`} fill={`url(#${id})`} />}
    <path d={line} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
  </svg>;
}

// series: [{ name, color, values }] over `labels` (ISO dates). format(value) for the tooltip.
export function LineChart({ labels, series, format = String }) {
  const [hover, setHover] = useState(null);
  const width = 700;
  const height = 260;
  const pad = { left: 38, right: 16, top: 16, bottom: 30 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const max = niceMax(Math.max(...series.flatMap((item) => item.values), 0));
  const x = (i) => pad.left + (labels.length > 1 ? (i / (labels.length - 1)) * innerW : innerW / 2);
  const y = (value) => pad.top + innerH - (value / max) * innerH;
  const ticks = [0, 1, 2, 3, 4].map((n) => (max / 4) * n);
  const every = Math.ceil(labels.length / 7);
  const label = (iso) => {
    const date = new Date(`${iso}T00:00:00Z`);
    return labels.length <= 7 ? date.toLocaleDateString(undefined, { weekday: "short", timeZone: "UTC" })
      : date.toLocaleDateString(undefined, { day: "numeric", month: "short", timeZone: "UTC" });
  };
  const move = (event) => {
    const box = event.currentTarget.getBoundingClientRect();
    const position = ((event.clientX - box.left) / box.width) * width;
    const index = Math.round(((position - pad.left) / innerW) * (labels.length - 1));
    setHover(Math.min(labels.length - 1, Math.max(0, index)));
  };
  return <div className="ad-chart">
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Chart of daily totals"
      onPointerMove={move} onPointerLeave={() => setHover(null)}>
      {ticks.map((tick) => <g key={tick}>
        <line x1={pad.left} x2={width - pad.right} y1={y(tick)} y2={y(tick)} className="ad-grid" />
        <text x={pad.left - 8} y={y(tick) + 4} textAnchor="end" className="ad-axis">{Math.round(tick * 100) / 100}</text>
      </g>)}
      {labels.map((iso, i) => i % every === 0 && <text key={iso} x={x(i)} y={height - 8} textAnchor="middle" className="ad-axis">{label(iso)}</text>)}
      {series.map((item) => {
        const points = item.values.map((value, i) => [x(i), y(value)]);
        const line = curve(points);
        return <g key={item.name}>
          {series.length === 1 && <path d={`${line} L${x(labels.length - 1)},${y(0)} L${x(0)},${y(0)} Z`} fill={item.color} opacity=".1" />}
          <path d={line} fill="none" stroke={item.color} strokeWidth="3" strokeLinecap="round" />
          {hover != null && <circle cx={x(hover)} cy={y(item.values[hover])} r="5" fill="#fff" stroke={item.color} strokeWidth="3" />}
        </g>;
      })}
      {hover != null && <line x1={x(hover)} x2={x(hover)} y1={pad.top} y2={y(0)} className="ad-cursor" />}
    </svg>
    {hover != null && <div className="ad-tooltip" style={{ left: `${(x(hover) / width) * 100}%` }} role="status">
      <strong>{label(labels[hover])}</strong>
      {series.map((item) => <span key={item.name}><i style={{ background: item.color }} />{item.name}: {format(item.values[hover], item)}</span>)}
    </div>}
  </div>;
}
