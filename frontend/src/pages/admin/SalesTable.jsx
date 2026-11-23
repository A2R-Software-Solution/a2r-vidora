const fmtMoney = (cents) => `$${((cents || 0) / 100).toFixed(2)}`;
const fmtMonth = (iso) => new Date(`${iso}T00:00:00`).toLocaleString("en-US", { month: "long", year: "numeric" });

// Credits sold (paid packs) and revenue per month, newest first.
export default function SalesTable({ rows }) {
  if (!rows) return <p className="ad-muted">Loading…</p>;
  if (rows.length === 0) return <p className="ad-na" role="status">N/A — no paid packs yet</p>;
  return (
    <div className="admin-table-wrap"><table className="admin-table">
      <thead><tr><th>Month</th><th>Credits sold</th><th>Payments</th><th>Revenue</th></tr></thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.month}>
            <td>{fmtMonth(row.month)}</td><td>{row.credits_sold}</td><td>{row.payments}</td><td>{fmtMoney(row.revenue_cents)}</td>
          </tr>))}
      </tbody>
    </table></div>
  );
}
