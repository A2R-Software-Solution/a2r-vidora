import { useCallback, useEffect, useState } from "react";
import { adjustCredits, getList, getOverview, getUserDetail } from "../api/adminApi";
import "./AdminPage.css";

const PAGE_SIZE = 25;
const fmtDate = (value) => (value ? new Date(value).toLocaleString() : "—");
const fmtMoney = (cents) => `$${((cents || 0) / 100).toFixed(2)}`;
const fmtDuration = (seconds) => (seconds == null ? "—" : `${Math.floor(seconds / 60)}m ${seconds % 60}s`);
const short = (id) => (id ? String(id).slice(0, 8) : "—");
const clip = (text, n = 80) => (text && text.length > n ? `${text.slice(0, n)}…` : text || "—");

function errorText(error) {
  if (error?.response?.status === 403) return "This account is not an admin.";
  if (error?.response?.status === 401) return "Sign in to continue.";
  return error?.response?.data?.detail || "Could not load data. Try again.";
}

// Each tab: API resource, optional status filter values and table columns.
const TABS = {
  users: {
    label: "Users", search: "Search email or user id",
    columns: [["Email", (r) => r.email], ["Plan", (r) => r.plan], ["Admin", (r) => (r.is_admin ? "yes" : "")],
      ["Purchased credits", (r) => r.purchased_balance], ["Joined", (r) => fmtDate(r.created_at)]],
  },
  payments: {
    label: "Payments", statuses: ["created", "paid", "failed", "refunded", "disputed"],
    columns: [["Email", (r) => r.email], ["Pack", (r) => r.pack_code], ["Credits", (r) => r.credits],
      ["Amount", (r) => fmtMoney(r.amount_cents)], ["Status", (r) => r.status],
      ["Payment id", (r) => r.provider_payment_id || r.provider_order_id], ["Created", (r) => fmtDate(r.created_at)]],
  },
  videos: {
    label: "Videos", search: "Search title or URL", statuses: ["processing", "completed", "failed"],
    columns: [["Title", (r) => clip(r.title || r.youtube_url, 50)], ["Status", (r) => r.status],
      ["Stage", (r) => r.processing_stage], ["Length", (r) => fmtDuration(r.duration)],
      ["Owner", (r) => (r.is_guest ? "guest" : short(r.user_id))], ["Priority", (r) => (r.priority ? "yes" : "")],
      ["Created", (r) => fmtDate(r.created_at)]],
  },
  shorts: {
    label: "Shorts", statuses: ["queued", "processing", "completed", "failed"],
    columns: [["Short", (r) => short(r.id)], ["Video", (r) => short(r.video_id)],
      ["Range", (r) => `${r.start_time}s–${r.end_time}s`], ["Status", (r) => r.status],
      ["Error", (r) => r.error_code || "—"], ["Created", (r) => fmtDate(r.created_at)]],
  },
  "qa-logs": {
    label: "Q&A logs", search: "Search question or answer",
    columns: [["User", (r) => r.email || "guest"], ["Question", (r) => clip(r.question, 90)],
      ["Answer", (r) => clip(r.answer, 90)], ["Asked", (r) => fmtDate(r.created_at)]],
  },
};

function Overview() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    getOverview(controller.signal).then((r) => setData(r.data)).catch((e) => {
      if (!controller.signal.aborted) setError(errorText(e));
    });
    return () => controller.abort();
  }, []);
  if (error) return <p className="admin-error" role="alert">{error}</p>;
  if (!data) return <p className="admin-muted">Loading…</p>;
  const videos = data.videos_by_status || {};
  const sttPct = Math.round((data.stt_seconds_24h / data.stt_seconds_limit_day) * 100);
  const tiles = [
    ["Users", data.users_total, `+${data.users_24h} in 24h`],
    ["Videos (24h)", data.videos_24h, `${videos.completed || 0} done · ${videos.processing || 0} running · ${videos.failed || 0} failed (all time)`],
    ["Revenue", fmtMoney(data.revenue_cents), `${fmtMoney(data.revenue_cents_24h)} in 24h · ${data.payments_paid} payments`],
    ["Credits outstanding", data.credits_outstanding, `${data.credits_spent_24h} spent in 24h`],
    ["STT audio (24h)", `${Math.round(data.stt_seconds_24h / 60)} min`, `${sttPct}% of the daily limit`],
    ["Shorts (24h)", data.shorts_24h, ""],
  ];
  return (
    <>
      <div className="admin-tiles">
        {tiles.map(([label, value, note]) => (
          <div className="admin-tile" key={label}>
            <span className="admin-tile-label">{label}</span>
            <strong>{value}</strong>
            {note && <span className="admin-muted">{note}</span>}
          </div>
        ))}
      </div>
      <h2>Failures in the last 24h, by stage</h2>
      {data.failures_24h_by_stage.length === 0 ? <p className="admin-muted">No failures.</p> : (
        <ul className="admin-plain">
          {data.failures_24h_by_stage.map((f) => <li key={f.stage}><strong>{f.count}</strong> {f.stage}</li>)}
        </ul>
      )}
    </>
  );
}

function Table({ columns, rows, onRowClick }) {
  if (rows.length === 0) return <p className="admin-muted">Nothing found.</p>;
  return (
    <div className="admin-table-wrap">
      <table className="admin-table">
        <thead><tr>{columns.map(([name]) => <th key={name}>{name}</th>)}</tr></thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className={onRowClick ? "is-clickable" : undefined}
              onClick={onRowClick && (() => onRowClick(row))}>
              {columns.map(([name, cell]) => <td key={name}>{cell(row)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ListTab({ resource, onOpenUser }) {
  const tab = TABS[resource];
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const params = { limit: PAGE_SIZE, offset };
    if (term) params.q = term;
    if (status) params.status = status;
    getList(resource, params, controller.signal).then((r) => { setRows(r.data); setError(""); }).catch((e) => {
      if (!controller.signal.aborted) setError(errorText(e));
    });
    return () => controller.abort();
  }, [resource, term, status, offset]);

  const submit = (event) => { event.preventDefault(); setOffset(0); setTerm(q.trim()); };

  return (
    <>
      <form className="admin-filters" onSubmit={submit}>
        {tab.search && <input type="search" value={q} onChange={(e) => setQ(e.target.value)}
          placeholder={tab.search} aria-label={tab.search} maxLength={100} />}
        {tab.statuses && (
          <select value={status} onChange={(e) => { setOffset(0); setStatus(e.target.value); }} aria-label="Status">
            <option value="">All statuses</option>
            {tab.statuses.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        )}
        {tab.search && <button type="submit">Search</button>}
      </form>
      {error ? <p className="admin-error" role="alert">{error}</p>
        : rows === null ? <p className="admin-muted">Loading…</p>
        : <Table columns={tab.columns} rows={rows} onRowClick={resource === "users" ? onOpenUser : undefined} />}
      <div className="admin-pager">
        <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button>
        <span className="admin-muted">Rows {offset + 1}–{offset + (rows?.length || 0)}</span>
        <button type="button" disabled={!rows || rows.length < PAGE_SIZE} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button>
      </div>
    </>
  );
}

function UserDetail({ userId, onBack }) {
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState("");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  const load = useCallback((signal) => getUserDetail(userId, signal)
    .then((r) => { setDetail(r.data); setError(""); })
    .catch((e) => { if (!signal?.aborted) setError(errorText(e)); }), [userId]);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  async function submit(event) {
    event.preventDefault();
    const credits = Number.parseInt(amount, 10);
    if (!credits || !window.confirm(`${credits > 0 ? "Grant" : "Remove"} ${Math.abs(credits)} credits for ${detail.email}?`)) return;
    setSaving(true);
    setMessage("");
    try {
      const { data } = await adjustCredits(userId, credits, reason.trim());
      setMessage(`Done. New purchased balance: ${data.purchased_balance}.`);
      setAmount("");
      setReason("");
      await load();
    } catch (e) {
      setMessage(e?.response?.status === 402 ? "Not enough purchased credits to remove that many." : errorText(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <button type="button" className="admin-link" onClick={onBack}>← Back to users</button>
      {error ? <p className="admin-error" role="alert">{error}</p> : !detail ? <p className="admin-muted">Loading…</p> : (
        <>
          <h2>{detail.email}</h2>
          <p className="admin-muted">
            {detail.plan} plan · joined {fmtDate(detail.created_at)}{detail.is_admin ? " · admin" : ""} · id {detail.id}
          </p>
          <div className="admin-tiles">
            <div className="admin-tile"><span className="admin-tile-label">Purchased credits</span>
              <strong>{detail.account?.purchased_balance ?? 0}</strong></div>
            <div className="admin-tile"><span className="admin-tile-label">Free used today</span>
              <strong>{detail.account?.daily_free_used ?? 0}</strong></div>
            <div className="admin-tile"><span className="admin-tile-label">Questions today</span>
              <strong>{detail.account?.daily_chat_used ?? 0}</strong></div>
          </div>

          <h3>Adjust credits</h3>
          <form className="admin-filters" onSubmit={submit}>
            <input type="number" value={amount} onChange={(e) => setAmount(e.target.value)}
              placeholder="+30 or -30" aria-label="Credits (negative to remove)" required />
            <input type="text" value={reason} onChange={(e) => setReason(e.target.value)}
              placeholder="Reason (saved in the ledger)" aria-label="Reason" minLength={3} maxLength={180} required />
            <button type="submit" disabled={saving}>{saving ? "Saving…" : "Apply"}</button>
          </form>
          {message && <p role="status">{message}</p>}

          <h3>Ledger (latest 50)</h3>
          <Table rows={detail.ledger} columns={[["When", (r) => fmtDate(r.created_at)], ["Kind", (r) => r.kind],
            ["Bucket", (r) => r.bucket], ["Amount", (r) => r.amount], ["Balance after", (r) => r.balance_after],
            ["Note", (r) => clip(r.note, 70)]]} />
          <h3>Payments</h3>
          <Table rows={detail.payments} columns={[["Pack", (r) => r.pack_code], ["Credits", (r) => r.credits],
            ["Amount", (r) => fmtMoney(r.amount_cents)], ["Status", (r) => r.status], ["Created", (r) => fmtDate(r.created_at)]]} />
          <h3>Recent videos</h3>
          <Table rows={detail.videos} columns={TABS.videos.columns.filter(([n]) => n !== "Owner")} />
        </>
      )}
    </>
  );
}

export default function AdminPage({ user, onSignIn }) {
  const [tab, setTab] = useState("overview");
  const [userId, setUserId] = useState(null);

  if (!user) {
    return (
      <section className="admin">
        <h1>Admin</h1>
        <p className="admin-muted">Sign in with an admin account to continue.</p>
        <button type="button" className="admin-button" onClick={onSignIn}>Sign in</button>
      </section>
    );
  }

  const open = (name) => { setUserId(null); setTab(name); };
  return (
    <section className="admin">
      <h1>Admin</h1>
      <div className="admin-tabs" role="tablist">
        {[["overview", "Overview"], ...Object.entries(TABS).map(([key, t]) => [key, t.label])].map(([key, label]) => (
          <button key={key} type="button" role="tab" aria-selected={tab === key} onClick={() => open(key)}>{label}</button>
        ))}
      </div>
      {tab === "overview" && <Overview />}
      {tab === "users" && (userId
        ? <UserDetail userId={userId} onBack={() => setUserId(null)} />
        : <ListTab resource="users" onOpenUser={(row) => setUserId(row.id)} />)}
      {tab !== "overview" && tab !== "users" && <ListTab key={tab} resource={tab} />}
    </section>
  );
}
