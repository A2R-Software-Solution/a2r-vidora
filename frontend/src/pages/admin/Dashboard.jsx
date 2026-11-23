import { useEffect, useRef, useState } from "react";
import { getActivity, getCreditsSummary, getOverview, getTimeseries } from "../../api/adminApi";
import SiteLink from "../../components/common/SiteLink";
import { config } from "../../config";
import Icon from "./Icon";
import SalesTable from "./SalesTable";
import { LineChart, Sparkline } from "./charts";

const RANGES = [[7, "Last 7 Days"], [30, "Last 30 Days"], [90, "Last 90 Days"]];
const fmtMoney = (cents) => `$${((cents || 0) / 100).toFixed(2)}`;
const NA = "N/A";
const sum = (values) => values.reduce((total, value) => total + value, 0);
const ACTIVITY = {
  user: ["users", "#2f7de1", "#e8f1fd"], short: ["video", "#ff6b35", "#ffece2"], video: ["chart", "#8b5cf6", "#f1ebfe"],
  credits: ["bolt", "#22a35a", "#e5f6ec"], settings: ["gear", "#7c5cd6", "#efeaff"],
};

function ago(iso) {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hour${hours > 1 ? "s" : ""} ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days > 1 ? "s" : ""} ago`;
}

// Loads once per dependency change; `load` gets an AbortSignal.
function useLoad(load, key) {
  const [state, setState] = useState({ key: null, data: null, error: "" });
  const latest = useRef(load);
  useEffect(() => { latest.current = load; });
  useEffect(() => {
    const controller = new AbortController();
    latest.current(controller.signal)
      .then((response) => setState({ key, data: response.data, error: "" }))
      .catch((error) => {
        if (controller.signal.aborted) return;
        setState({ key, data: null, error: error?.response?.status === 403 ? "This account is not an admin." : "Could not load this." });
      });
    return () => controller.abort();
  }, [key]);
  return state.key === key ? state : { key, data: null, error: "" };
}

const loadOverview = (signal) => getOverview(signal);
const loadActivity = (signal) => getActivity(8, signal);
const loadCredits = (signal) => getCreditsSummary(signal);

const CREDIT_ROWS = [
  ["Free credits given", "free_given", "Signups x current bonus (estimate if the bonus changed)"],
  ["Purchased credits given", "purchased_given", "From paid packs"],
  ["Added by admin", "admin_added", "Manual grants"],
  ["Total given", "total_given", null, true],
  ["Free credits used", "free_used", "Net of refunds for failed jobs"],
  ["Purchased credits used", "purchased_used", "Net of refunds for failed jobs"],
  ["Total used", "total_used", null, true],
];

function CreditsCard({ credits }) {
  const c = credits.data;
  const percent = (value) => (value == null ? NA : `${value}%`);
  return <section className="ad-card ad-credits" aria-labelledby="ad-credits">
    <div className="ad-card-head"><h2 id="ad-credits"><Icon name="bolt" size={20} /> Credits Given vs Used</h2>
      {c && <span className="ad-muted">{c.free_bonus_per_user} free signup credits per user (one time) · signed-in users only</span>}</div>
    {credits.error ? <p className="admin-error" role="alert">{credits.error}</p> : !c ? <p className="ad-muted">Loading…</p> : (
      <div className="admin-table-wrap"><table className="admin-table">
        <thead><tr><th>Credits</th><th>This month</th><th>All time</th></tr></thead>
        <tbody>
          {CREDIT_ROWS.map(([label, key, note, bold]) => (
            <tr key={key} className={bold ? "ad-credits-total" : undefined}>
              <td>{label}{note && <span className="ad-muted ad-credits-note">{note}</span>}</td>
              <td>{c.this_month[key]}</td><td>{c.all_time[key]}</td>
            </tr>))}
          <tr><td>Used of given</td><td>{percent(c.this_month.used_percent)}</td><td>{percent(c.all_time.used_percent)}</td></tr>
          <tr><td>Purchased credits still unspent<span className="ad-muted ad-credits-note">Users&apos; remaining balance</span></td>
            <td colSpan={2}>{c.purchased_outstanding}</td></tr>
        </tbody>
      </table></div>)}
    {c && <><h3 className="ad-credits-sub">Credits sold per month</h3><SalesTable rows={c.sales_by_month} /></>}
  </section>;
}

function Stat({ icon, tint, color, label, value, chip, chipTone = "up", action, spark }) {
  return <div className="ad-stat">
    <div className="ad-stat-top">
      <span className="ad-stat-icon" style={{ background: tint, color }}><Icon name={icon} size={26} /></span>
      <div><span className="ad-stat-label">{label}</span><strong>{value}</strong></div>
      {action ? <button type="button" className="ad-chip ad-chip--action" onClick={action.run}>{action.label}</button>
        : chip && <span className={`ad-chip ad-chip--${chipTone}`}>{chip}</span>}
    </div>
    {spark && <Sparkline values={spark} color={color} />}
  </div>;
}

export default function Dashboard({ user, go }) {
  const [days, setDays] = useState(7);
  const [view, setView] = useState("overview");
  const overview = useLoad(loadOverview, "overview");
  const loadSeries = (signal) => getTimeseries(days, signal);
  const series = useLoad(loadSeries, days);
  const activity = useLoad(loadActivity, "activity");
  const credits = useLoad(loadCredits, "credits");
  const name = (user?.displayName || "Admin").split(" ")[0];
  const o = overview.data;
  const s = series.data;

  const charts = s && {
    overview: [{ name: "Users", color: "#ff6b35", values: s.users }, { name: "Videos", color: "#8b5cf6", values: s.videos }],
    users: [{ name: "Users", color: "#ff6b35", values: s.users }],
    videos: [{ name: "Videos", color: "#8b5cf6", values: s.videos }],
    revenue: [{ name: "Revenue", color: "#22a35a", values: s.revenue_cents }],
  };
  const tooltipValue = (value, item) => (item.name === "Revenue" ? fmtMoney(value) : value);

  return <>
    <div className="ad-welcome">
      <div><h1>Welcome back, {name}! <span aria-hidden="true">👋</span></h1>
        <p>Here&apos;s what&apos;s happening with Vidora AI today.</p></div>
      <label className="ad-range"><Icon name="calendar" size={18} />
        <select value={days} onChange={(event) => setDays(Number(event.target.value))} aria-label="Date range">
          {RANGES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
    </div>
    {overview.error && <p className="admin-error" role="alert">{overview.error}</p>}

    <div className="ad-stats">
      <Stat icon="users" tint="#ffece2" color="#ff6b35" label="Users" value={o ? o.users_total : "…"}
        chip={o && (o.users_24h > 0 ? `+${o.users_24h} today` : NA)} chipTone={o?.users_24h > 0 ? "up" : "flat"} spark={s?.users} />
      <Stat icon="video" tint="#f1ebfe" color="#8b5cf6" label="Videos (24h)" value={o ? o.videos_24h : "…"}
        chip={o && (o.videos_by_status?.failed > 0 ? `${o.videos_by_status.failed} failed` : NA)}
        chipTone={o?.videos_by_status?.failed > 0 ? "down" : "flat"} spark={s?.videos} />
      <Stat icon="card" tint="#e5f6ec" color="#22a35a" label="Revenue" value={o ? fmtMoney(o.revenue_cents) : "…"}
        chip={o && (o.revenue_cents_24h > 0 ? `${fmtMoney(o.revenue_cents_24h)} today` : NA)} chipTone="flat" spark={s?.revenue_cents} />
      <Stat icon="bolt" tint="#e8f1fd" color="#2f7de1" label="Credits Remaining" value={o ? o.credits_outstanding : "…"}
        action={{ label: "Add Credits", run: () => go("users") }} spark={s?.credits_spent} />
    </div>

    <div className="ad-row">
      <section className="ad-card" aria-labelledby="ad-analytics">
        <div className="ad-card-head"><h2 id="ad-analytics"><Icon name="chart" size={20} /> Analytics Overview</h2>
          {s && <span className="ad-muted">{sum(s.users)} new users · {sum(s.videos)} videos · {fmtMoney(sum(s.revenue_cents))} in {days} days</span>}</div>
        <div className="ad-pills" role="tablist" aria-label="Chart">
          {[["overview", "Overview"], ["users", "Users"], ["videos", "Videos"], ["revenue", "Revenue"]].map(([key, label]) => (
            <button key={key} type="button" role="tab" aria-selected={view === key} onClick={() => setView(key)}>{label}</button>))}
        </div>
        {series.error ? <p className="admin-error" role="alert">{series.error}</p> : !s ? <p className="ad-muted">Loading…</p>
          : charts[view].every((item) => sum(item.values) === 0) ? <p className="ad-na" role="status">{NA} — no data in this period</p> : <>
          {view === "overview" && <p className="ad-legend"><i style={{ background: "#ff6b35" }} />Users <i style={{ background: "#8b5cf6" }} />Videos</p>}
          <LineChart labels={s.days} series={charts[view]} format={tooltipValue} /></>}
      </section>

      <section className="ad-card" aria-labelledby="ad-activity">
        <div className="ad-card-head"><h2 id="ad-activity"><Icon name="bolt" size={20} /> Recent Activity</h2></div>
        {activity.error ? <p className="admin-error" role="alert">{activity.error}</p> : !activity.data ? <p className="ad-muted">Loading…</p>
          : activity.data.length === 0 ? <p className="ad-na" role="status">{NA}</p> : (
          <ul className="ad-feed">
            {activity.data.map((event, index) => {
              const [icon, color, tint] = ACTIVITY[event.type] || ACTIVITY.settings;
              return <li key={`${event.at}-${index}`}>
                <span className="ad-feed-icon" style={{ background: tint, color }}><Icon name={icon} size={20} /></span>
                <div><strong>{event.title}</strong><span className="ad-muted">{ago(event.at)}{event.detail ? ` · ${event.detail}` : ""}</span></div>
              </li>;
            })}
          </ul>)}
      </section>
    </div>

    <CreditsCard credits={credits} />

    <div className="ad-row ad-row--bottom">
      <section className="ad-card" aria-labelledby="ad-quick">
        <div className="ad-card-head"><h2 id="ad-quick"><Icon name="star" size={20} /> Quick Actions</h2></div>
        <div className="ad-quick">
          <SiteLink href="/reels" className="ad-quick-item ad-quick-item--orange"><Icon name="camera" /> Create Reel <Icon name="arrow" size={16} /></SiteLink>
          <SiteLink href="/analyze" className="ad-quick-item ad-quick-item--purple"><Icon name="chart" /> Analyze Videos <Icon name="arrow" size={16} /></SiteLink>
          <button type="button" className="ad-quick-item ad-quick-item--blue" onClick={() => go("settings")}><Icon name="gear" /> Manage Settings <Icon name="arrow" size={16} /></button>
          <button type="button" className="ad-quick-item ad-quick-item--green" onClick={() => go("users")}><Icon name="card" /> Add Credits <Icon name="arrow" size={16} /></button>
        </div>
      </section>
      <section className="ad-card ad-help" aria-labelledby="ad-help">
        <h2 id="ad-help"><Icon name="help" size={20} /> Need Help?</h2>
        <p className="ad-muted">Report a problem or send us feedback.</p>
        <a className="ad-chip ad-chip--action" href={config.bugReportUrl} target="_blank" rel="noopener noreferrer">Contact Support <Icon name="arrow" size={14} /></a>
      </section>
    </div>
  </>;
}
