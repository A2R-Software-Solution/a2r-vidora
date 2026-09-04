export default function Navbar({ onHome }) {
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
      <div className="nav-right"></div>
    </nav>
  );
}