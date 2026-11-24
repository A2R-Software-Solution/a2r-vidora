import { useCallback, useEffect, useState } from "react";
import {
  adjustCredits, banUser, createCoupon, getCoupons, getCreditsSummary, getList, getSettings, getUserDetail,
  saveSettings, unbanUser, updateCoupon,
} from "../api/adminApi";
import { signOut } from "firebase/auth";
import { auth } from "../firebase";
import SiteLink from "../components/common/SiteLink";
import { config } from "../config";
import Dashboard from "./admin/Dashboard";
import Icon from "./admin/Icon";
import SalesTable from "./admin/SalesTable";
import { PACK_DETAILS, formatPrice } from "../utils/pricing";
import "./AdminPage.css";

const PAGE_SIZE = 25;
const fmtDate = (value) => (value ? new Date(value).toLocaleString() : "—");
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
      ["Amount", (r) => formatPrice(r.amount_cents, r.currency || "USD")], ["Status", (r) => r.status],
      ["Coupon", (r) => r.coupon_code || ""],
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

function PaymentsSummary() {
  const [rows, setRows] = useState(null);
  useEffect(() => {
    const controller = new AbortController();
    getCreditsSummary(controller.signal).then((r) => setRows(r.data.sales_by_month)).catch(() => {
      if (!controller.signal.aborted) setRows([]);
    });
    return () => controller.abort();
  }, []);
  return <><h2>Credits sold per month</h2><SalesTable rows={rows} /><h2>All payments</h2></>;
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
            ["Amount", (r) => formatPrice(r.amount_cents, r.currency || "USD")], ["Status", (r) => r.status], ["Created", (r) => fmtDate(r.created_at)]]} />
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
  "Free signup credits": "A one-time bonus for every signed-in user; it never renews. Applies immediately, and credits a user already used still count against the new amount.",
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
                      {row.unit}{value !== "" && (row.unit === "US cents" || row.unit === "paise")
                        ? ` (${formatPrice(Number(value), row.unit === "paise" ? "INR" : "USD")})` : ""}
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

// An expiry date picked in the form means the end of that day, in the admin's time zone.
const pad = (n) => String(n).padStart(2, "0");
const toDateInput = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};
const fromDateInput = (day) => (day ? new Date(`${day}T23:59:59`).toISOString() : null);
const optionalNumber = (text) => (text === "" ? null : Number(text));

const EMPTY_COUPON = { code: "", percent_off: "50", bonus_credits: "0", packs: [], currency: "",
  max_uses: "", per_user_limit: "1", expires: "", note: "" };

function couponDraft(c) {
  return { code: c.code, percent_off: String(c.percent_off), bonus_credits: String(c.bonus_credits),
    packs: c.packs || [], currency: c.currency || "", max_uses: c.max_uses == null ? "" : String(c.max_uses),
    per_user_limit: c.per_user_limit == null ? "" : String(c.per_user_limit),
    expires: toDateInput(c.expires_at), note: c.note || "" };
}

function couponBenefit(c) {
  return [c.percent_off > 0 && `${c.percent_off}% off`, c.bonus_credits > 0 && `+${c.bonus_credits} credits`]
    .filter(Boolean).join(", ");
}

function CouponForm({ editing, onSaved, onCancel }) {
  const [draft, setDraft] = useState(editing ? couponDraft(editing) : EMPTY_COUPON);
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const set = (key) => (e) => setDraft({ ...draft, [key]: e.target.value });
  const togglePack = (code) => setDraft({ ...draft,
    packs: draft.packs.includes(code) ? draft.packs.filter((p) => p !== code) : [...draft.packs, code] });

  const save = async (event) => {
    event.preventDefault();
    const fields = {
      percent_off: Number(draft.percent_off), bonus_credits: Number(draft.bonus_credits),
      packs: draft.packs.length ? draft.packs : null, currency: draft.currency || null,
      max_uses: optionalNumber(draft.max_uses), per_user_limit: optionalNumber(draft.per_user_limit),
      expires_at: fromDateInput(draft.expires), note: draft.note.trim() || null,
    };
    setSaving(true);
    setMessage("");
    try {
      if (editing) await updateCoupon(editing.id, fields);
      else await createCoupon({ ...fields, code: draft.code.trim() });
      onSaved();
    } catch (e) {
      setMessage(errorText(e));
      setSaving(false);
    }
  };

  return (
    <form className="admin-coupon-form" onSubmit={save}>
      <h2>{editing ? `Edit ${editing.code}` : "New coupon"}</h2>
      <div className="admin-settings">
        <label className="admin-setting">Code
          <input value={draft.code} onChange={set("code")} required minLength={3} maxLength={40}
            pattern="[A-Za-z0-9_\-]+" disabled={!!editing} placeholder="LAUNCH50" />
          <span className="admin-muted">Letters, numbers, - and _. Buyers can type it in any case.</span></label>
        <label className="admin-setting">Discount
          <span className="admin-setting-input"><input type="number" min="0" max="100" step="1" required
            value={draft.percent_off} onChange={set("percent_off")} /><span className="admin-muted">% off</span></span>
          <span className="admin-muted">The price never goes below ₹1 / $1. 100 makes a ₹1 test coupon.</span></label>
        <label className="admin-setting">Bonus credits
          <span className="admin-setting-input"><input type="number" min="0" max="100000" step="1" required
            value={draft.bonus_credits} onChange={set("bonus_credits")} /><span className="admin-muted">extra credits</span></span></label>
        <fieldset className="admin-setting"><legend>Packs</legend>
          {Object.entries(PACK_DETAILS).map(([code, { name }]) => (
            <label key={code}><input type="checkbox" checked={draft.packs.includes(code)}
              onChange={() => togglePack(code)} /> {name}</label>))}
          <span className="admin-muted">None ticked: every pack.</span></fieldset>
        <label className="admin-setting">Currency
          <select value={draft.currency} onChange={set("currency")}>
            <option value="">Both (₹ and $)</option><option value="INR">Only ₹ (India)</option>
            <option value="USD">Only $</option></select></label>
        <label className="admin-setting">Total uses
          <input type="number" min="1" step="1" value={draft.max_uses} onChange={set("max_uses")} placeholder="No limit" />
          <span className="admin-muted">Paid purchases allowed in all. Empty: no limit.</span></label>
        <label className="admin-setting">Uses per user
          <input type="number" min="1" step="1" value={draft.per_user_limit} onChange={set("per_user_limit")} placeholder="No limit" />
          <span className="admin-muted">Empty: no limit.</span></label>
        <label className="admin-setting">Expires after
          <input type="date" value={draft.expires} onChange={set("expires")} />
          <span className="admin-muted">Works until the end of this day. Empty: never expires.</span></label>
        <label className="admin-setting">Note
          <input value={draft.note} onChange={set("note")} maxLength={200} placeholder="Who it is for (only admins see this)" /></label>
      </div>
      <div className="admin-savebar">
        <button type="submit" className="admin-button" disabled={saving}>{saving ? "Saving…" : editing ? "Save changes" : "Create coupon"}</button>
        <button type="button" className="admin-link" onClick={onCancel}>Cancel</button>
        {message && <span role="alert">{message}</span>}
      </div>
    </form>
  );
}

function Coupons() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");
  const [form, setForm] = useState(null); // null, "new" or the coupon being edited
  const [busy, setBusy] = useState("");

  const load = useCallback((signal) => getCoupons(signal).then((r) => setRows(r.data)).catch((e) => {
    if (!signal?.aborted) setError(errorText(e));
  }), []);
  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const toggle = async (coupon) => {
    if (coupon.active && !window.confirm(`Turn off ${coupon.code}? Buyers can no longer use it.`)) return;
    setBusy(coupon.id);
    try {
      await updateCoupon(coupon.id, { active: !coupon.active });
      await load();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy("");
    }
  };

  if (error) return <p className="admin-error" role="alert">{error}</p>;
  if (!rows) return <p className="admin-muted">Loading…</p>;
  const expired = (c) => c.expires_at && new Date(c.expires_at) <= new Date();
  return (
    <>
      <p className="admin-muted">Buyers enter a coupon on the pricing page. A use counts once the payment is made.
        Coupons are turned off, never deleted, so past payments keep their coupon.</p>
      {form
        ? <CouponForm key={form === "new" ? "new" : form.id} editing={form === "new" ? null : form}
            onCancel={() => setForm(null)} onSaved={() => { setForm(null); load(); }} />
        : <button type="button" className="admin-button" onClick={() => setForm("new")}>New coupon</button>}
      <h2>All coupons</h2>
      <Table rows={rows} columns={[
        ["Code", (c) => <strong>{c.code}</strong>], ["Gives", couponBenefit],
        ["Packs", (c) => (c.packs ? c.packs.map((p) => PACK_DETAILS[p]?.name || p).join(", ") : "All")],
        ["Currency", (c) => c.currency || "Both"],
        ["Used", (c) => `${c.uses}${c.max_uses ? ` / ${c.max_uses}` : ""}`],
        ["Per user", (c) => c.per_user_limit ?? "No limit"],
        ["Revenue", (c) => Object.entries(c.revenue).map(([cur, amt]) => formatPrice(amt, cur)).join(" + ") || "—"],
        ["Expires", (c) => (c.expires_at ? fmtDate(c.expires_at) : "Never")],
        ["Status", (c) => (!c.active ? "Off" : expired(c) ? "Expired" : c.max_uses && c.uses >= c.max_uses ? "Used up" : "Active")],
        ["Note", (c) => clip(c.note, 40)],
        ["", (c) => (
          <span className="admin-coupon-actions">
            <button type="button" className="admin-link" onClick={() => setForm(c)}>Edit</button>
            <button type="button" className="admin-link" disabled={busy === c.id} onClick={() => toggle(c)}>
              {c.active ? "Turn off" : "Turn on"}</button>
          </span>)],
      ]} />
    </>
  );
}

const NAV = [["overview", "Dashboard", "home"], ["users", "Users", "users"], ["payments", "Payments", "card"],
  ["coupons", "Coupons", "star"],
  ["videos", "Videos", "video"], ["shorts", "Shorts", "bolt"], ["qa-logs", "Q&A Logs", "chat"], ["settings", "Settings", "gear"]];

export default function AdminPage({ user, onSignIn }) {
  const [tab, setTab] = useState("overview");
  const [userId, setUserId] = useState(null);
  const [menuOpen, setMenuOpen] = useState(false);

  if (!user) {
    return (
      <section className="ad-signin">
        <h1>Admin</h1>
        <p className="admin-muted">Sign in with an admin account to continue.</p>
        <button type="button" className="admin-button" onClick={onSignIn}>Sign in</button>
      </section>
    );
  }

  const open = (name) => {
    setUserId(null);
    setTab(name);
    setMenuOpen(false);
    // A new section starts at the top, not wherever the last one was scrolled to.
    window.scrollTo({ top: 0 });
  };
  const title = NAV.find(([key]) => key === tab)?.[1];
  const name = user.displayName || user.email || "Admin";
  return (
    <div className="ad-shell admin">
      <aside className={`ad-side${menuOpen ? " is-open" : ""}`}>
        <div className="ad-side-top">
          <span className="ad-logo"><span className="ad-logo-mark" aria-hidden="true" /> Vidora <b>AI</b></span>
          <button type="button" className="ad-menu" aria-label="Menu" aria-expanded={menuOpen} onClick={() => setMenuOpen((value) => !value)}><Icon name="menu" /></button>
        </div>
        <nav className="ad-nav" aria-label="Admin">
          {NAV.map(([key, label, icon]) => (
            <button key={key} type="button" aria-current={tab === key ? "page" : undefined} onClick={() => open(key)}>
              <Icon name={icon} />{label}</button>
          ))}
        </nav>
        <div className="ad-side-foot">
          <a href={config.bugReportUrl} target="_blank" rel="noopener noreferrer"><Icon name="help" />Help &amp; Support</a>
          <SiteLink href="/"><Icon name="arrow" />Back to site</SiteLink>
          <button type="button" onClick={() => signOut(auth)}><Icon name="logout" />Logout</button>
        </div>
      </aside>
      <main className="ad-main">
        <div className="ad-topbar"><span className="ad-account"><span className="ad-avatar" aria-hidden="true">{name[0].toUpperCase()}</span>{name}</span></div>
        {tab === "overview" && <Dashboard user={user} go={open} />}
        {tab !== "overview" && <h1 className="ad-title">{title}</h1>}
        {tab === "users" && (userId
          ? <UserDetail userId={userId} onBack={() => setUserId(null)} />
          : <ListTab resource="users" onOpenUser={(row) => setUserId(row.id)} />)}
        {tab === "settings" && <Settings />}
        {tab === "coupons" && <Coupons />}
        {tab === "payments" && <PaymentsSummary />}
        {TABS[tab] && tab !== "users" && <ListTab key={tab} resource={tab} />}
      </main>
    </div>
  );
}
