import { signOut } from "firebase/auth";
import { auth } from "../../firebase";
import SiteLink from "../common/SiteLink";
import { useCredits } from "../../hooks/useCredits";
import "./Navbar.css";

export default function Navbar({ onHome, user, onAuth, currentPath }) {
  const credits = useCredits();
  return (
    <nav className="site-navbar" aria-label="Main navigation">
      <SiteLink className="logo" href="/" onClick={onHome} aria-label="Vidora AI home">
        <span className="logo-icon">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path d="M8 5v14l11-7-11-7z" fill="currentColor" />
          </svg>
        </span>
        Vidora<span>AI</span>
      </SiteLink>
      <div className="nav-right">
        <div className="tool-navigation">
          <SiteLink className="tool-link" href="/reels" aria-current={currentPath === "/reels" ? "page" : undefined}>Create Reel</SiteLink>
          <SiteLink className="tool-link" href="/analyze" aria-current={currentPath === "/analyze" ? "page" : undefined}>Analyze</SiteLink>
          <SiteLink className="tool-link" href="/song-merger" aria-current={currentPath === "/song-merger" ? "page" : undefined}>Song Merger <span className="new-tag">New</span></SiteLink>
          <SiteLink className="tool-link" href="/pricing" aria-current={currentPath === "/pricing" ? "page" : undefined}>Pricing</SiteLink>
        </div>
        {credits && (
          <SiteLink className="credit-chip" href="/pricing"
            aria-label={`${credits.available} credits available. View pricing`}>
            <span aria-hidden="true">⚡</span> {credits.available}<span className="credit-chip-label"> credits</span>
          </SiteLink>
        )}
        {user ? (
          <button type="button" className="signup" onClick={() => signOut(auth)}>Log out</button>
        ) : (
          <button
            type="button"
            className="nav-auth-button"
            onClick={onAuth}
            aria-label="Log in or sign up"
            aria-haspopup="dialog"
          >
            <span className="nav-auth-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" focusable="false">
                <circle cx="12" cy="8" r="3.25" />
                <path d="M5.5 20v-1.5a6.5 6.5 0 0 1 13 0V20" />
              </svg>
            </span>
            <span className="nav-auth-label">Account</span>
            <svg className="nav-auth-arrow" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">
              <path d="M5 12h14m-6-6 6 6-6 6" />
            </svg>
          </button>
        )}
      </div>
    </nav>
  );
}
