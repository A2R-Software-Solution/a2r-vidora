import { useCallback, useEffect, useState } from "react";
import { adjustCredits, banUser, getList, getOverview, getSettings, getUserDetail, saveSettings, unbanUser } from "../api/adminApi";
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
  const detail = error?.response?.data?.detail;
  return typeof detail === "string" ? detail : "The request failed. Try again.";
}

// Each tab: API resource, optional status filter values and table columns.
const TABS = {
  users: {
    label: "Users", search: "Search email or user id",
    columns: [["Email", (r) => r.email], ["Status", (r) => (r.banned ? "Banned" : r.is_admin ? "Admin" : "")],
      ["Credits left", (r) => r.available], ["Purchased", (r) => r.purchased_balance],
      ["Free left", (r) => r.free_left], ["Plan", (r) => r.plan], ["Joined", (r) => fmtDate(r.created_at)]],
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
  const [banReason, setBanReason] = useState("");
  const [banning, setBanning] = useState(false);
  const [banMessage, setBanMessage] = useState("");

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

  async function ban(event) {
    event.preventDefault();
    const reason = banReason.trim();
    if (reason.length < 3 || !window.confirm(`Ban ${detail.email}?

They will see this message:
${reason}`)) return;
    setBanning(true);
    setBanMessage("");
    try {
      await banUser(userId, reason);
      setBanReason("");
      setBanMessage("User banned. They see your message the next time the app talks to the server.");
      await load();
    } catch (e) {
      setBanMessage(errorText(e));
    } finally {
      setBanning(false);
    }
  }

  async function unban() {
    if (!window.confirm(`Unban ${detail.email}?`)) return;
    setBanning(true);
    setBanMessage("");
    try {
      await unbanUser(userId);
      setBanMessage("User unbanned.");
      await load();
    } catch (e) {
      setBanMessage(errorText(e));
    } finally {
      setBanning(false);
    }
  }

  return (
    <>
      <button type="button" className="admin-link" onClick={onBack}>← Back to users</button>
      {error ? <p className="admin-error" role="alert">{error}</p> : !detail ? <p className="admin-muted">Loading…</p> : (
        <>
          <h2>{detail.email}{detail.banned ? " · BANNED" : ""}</h2>
          <p className="admin-muted">
            {detail.plan} plan · joined {fmtDate(detail.created_at)}{detail.is_admin ? " · admin" : ""} · id {detail.id}
          </p>
          <div className="admin-tiles">
            <div className="admin-tile"><span className="admin-tile-label">Purchased credits</span>
              <strong>{detail.account?.purchased_balance ?? 0}</strong></div>
            <div className="admin-tile"><span className="admin-tile-label">Free used this month</span>
              <strong>{detail.account?.free_used ?? 0}</strong></div>
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

          <h3>Ban</h3>
          {detail.banned ? (
            <>
              <p className="admin-error">Banned {fmtDate(detail.banned_at)}. The user sees: “{detail.ban_reason}”</p>
              <button type="button" className="admin-button" onClick={unban} disabled={banning}>{banning ? "Saving…" : "Unban user"}</button>
            </>
          ) : detail.is_admin ? <p className="admin-muted">Admins cannot be banned.</p> : (
            <form className="admin-filters" onSubmit={ban}>
              <input type="text" value={banReason} onChange={(e) => setBanReason(e.target.value)}
                placeholder="Message the user will see (why they are banned)" aria-label="Ban message"
                minLength={3} maxLength={300} required />
              <button type="submit" disabled={banning}>{banning ? "Saving…" : "Ban user"}</button>
            </form>
          )}
          {banMessage && <p role="status">{banMessage}</p>}

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

const SETTING_NOTES = {
  "Retention": "Applies to items created after the change. Existing items keep their expiry time.",
  "Credit packs": "Applies to new purchases. Past payments keep the price and credits they were bought with.",
  "Free credits per month": "Applies immediately. Credits already used this month still count against the new limit.",
};

function Settings() {
  const [rows, setRows] = useState(null);
  const [draft, setDraft] = useState({});
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    getSettings(controller.signal).then((r) => setRows(r.data)).catch((e) => {
      if (!controller.signal.aborted) setError(errorText(e));
    });
    return () => controller.abort();
  }, []);

  if (error) return <p className="admin-error" role="alert">{error}</p>;
  if (!rows) return <p className="admin-muted">Loading…</p>;

  const changes = rows.filter((row) => draft[row.key] !== undefined && draft[row.key] !== ""
    && Number(draft[row.key]) !== row.value);
  const groups = [...new Set(rows.map((row) => row.group))];
  const describe = (row, value) => `${row.group} / ${row.label}: ${row.value} → ${value}`;

  async function apply(values, summary) {
    if (!window.confirm(`Apply these changes for all users?\n\n${summary}`)) return;
    setSaving(true);
    setMessage("");
    try {
      const { data } = await saveSettings(values);
      setRows(data);
      setDraft({});
      setMessage("Saved. Every server picks the change up within 30 seconds.");
    } catch (e) {
      setMessage(errorText(e));
    } finally {
      setSaving(false);
    }
  }

  const save = (event) => {
    event.preventDefault();
    apply(Object.fromEntries(changes.map((row) => [row.key, Number(draft[row.key])])),
      changes.map((row) => describe(row, draft[row.key])).join("\n"));
  };

  return (
    <form onSubmit={save}>
      <p className="admin-muted">Limits and prices used across the app. A change applies to everyone, without a deploy.</p>
      {groups.map((group) => (
        <section key={group}>
          <h2>{group}</h2>
          {SETTING_NOTES[group] && <p className="admin-muted">{SETTING_NOTES[group]}</p>}
          <div className="admin-settings">
            {rows.filter((row) => row.group === group).map((row) => {
              const value = draft[row.key] ?? String(row.value);
              return (
                <div className="admin-setting" key={row.key}>
                  <label htmlFor={`setting-${row.key}`}>{row.label}</label>
                  <span className="admin-setting-input">
                    <input id={`setting-${row.key}`} type="number" inputMode="numeric" step="1" required
                      min={row.minimum} max={row.maximum} value={value}
                      onChange={(e) => setDraft({ ...draft, [row.key]: e.target.value })} />
                    <span className="admin-muted">
                      {row.unit}{row.unit === "US cents" && value !== "" ? ` (${fmtMoney(Number(value))})` : ""}
                    </span>
                  </span>
                  <span className="admin-muted">
                    {row.overridden
                      ? <>Default {row.default} · changed by {row.updated_by}, {fmtDate(row.updated_at)} ·{" "}
                        <button type="button" className="admin-link" disabled={saving}
                          onClick={() => apply({ [row.key]: null }, describe(row, `${row.default} (default)`))}>
                          Reset
                        </button></>
                      : "Default"}
                  </span>
                </div>
              );
            })}
          </div>
        </section>
      ))}
      <div className="admin-savebar">
        <button type="submit" className="admin-button" disabled={saving || changes.length === 0}>
          {saving ? "Saving…" : changes.length ? `Save ${changes.length} change${changes.length > 1 ? "s" : ""}` : "No changes"}
        </button>
        {changes.length > 0 && <button type="button" className="admin-link" onClick={() => setDraft({})}>Discard</button>}
        {message && <span role="status">{message}</span>}
      </div>
    </form>
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
        {[["overview", "Overview"], ...Object.entries(TABS).map(([key, t]) => [key, t.label]), ["settings", "Settings"]].map(([key, label]) => (
          <button key={key} type="button" role="tab" aria-selected={tab === key} onClick={() => open(key)}>{label}</button>
        ))}
      </div>
      {tab === "overview" && <Overview />}
      {tab === "users" && (userId
        ? <UserDetail userId={userId} onBack={() => setUserId(null)} />
        : <ListTab resource="users" onOpenUser={(row) => setUserId(row.id)} />)}
      {tab === "settings" && <Settings />}
      {TABS[tab] && tab !== "users" && <ListTab key={tab} resource={tab} />}
    </section>
  );
}
