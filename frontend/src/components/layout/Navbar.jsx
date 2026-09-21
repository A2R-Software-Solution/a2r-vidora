import { signOut } from "firebase/auth";
import { auth } from "../../firebase";
import "./Navbar.css";

export default function Navbar({ onHome, user, onAuth }) {
  return (
    <nav>
      <div className="logo" onClick={onHome} role="button" tabIndex={0}>
        <span className="logo-icon">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path d="M8 5v14l11-7-11-7z" fill="currentColor" />
          </svg>
        </span>
        Vidora<span>AI</span>
      </div>
      <div className="nav-right">
        {user ? (
          <>
            <span className="nav-email">{user.email}</span>
            <button type="button" className="signup" onClick={() => signOut(auth)}>Log out</button>
          </>
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
