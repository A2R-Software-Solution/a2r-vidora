import { signOut } from "firebase/auth";
import { auth } from "../../firebase";
import { clearBanNotice, useBanNotice } from "../../utils/banNotice";
import "./BannedNotice.css";

export default function BannedNotice() {
  const notice = useBanNotice();
  if (!notice) return null;
  const leave = async () => {
    try { await signOut(auth); } finally { clearBanNotice(); }
  };
  return <div className="ban-overlay" role="alertdialog" aria-modal="true" aria-labelledby="ban-title" aria-describedby="ban-reason">
    <div className="ban-card">
      <h2 id="ban-title">Your account has been suspended</h2>
      <p id="ban-reason" className="ban-reason">{notice.reason}</p>
      <p className="ban-note">You can't use Vidora AI with this account. If you think this is a mistake, contact support.</p>
      <button type="button" onClick={leave}>Sign out</button>
    </div>
  </div>;
}
