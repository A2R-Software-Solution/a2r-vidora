import { useEffect, useState } from "react";
import { onAuthStateChanged } from "firebase/auth";
import { auth } from "./firebase";
import AuthModal from "./components/auth/AuthModal";
import Navbar from "./components/layout/Navbar";
import LandingPage from "./pages/LandingPage";
import WorkspacePage from "./pages/WorkspacePage";
import SpotlightGlow from "./components/common/SpotlightGlow";
import BugReportButton from "./components/common/BugReportButton";
import "./App.css";

function App() {
  const [video, setVideo] = useState(null);
  const [user, setUser] = useState(null);
  const [authOpen, setAuthOpen] = useState(false);

  useEffect(() => onAuthStateChanged(auth, setUser), []);

  return (
    <div className="page">
      <div className="floating-bubbles" aria-hidden="true">
        <span className="bubble b1"></span>
        <span className="bubble b2"></span>
        <span className="bubble b3"></span>
        <span className="bubble b4"></span>
      </div>
      <SpotlightGlow />
      <Navbar onHome={() => setVideo(null)} user={user} onAuth={() => setAuthOpen(true)} />
      <LandingPage onAnalyzed={setVideo} compact={!!video} />
      {video && <WorkspacePage video={video} />}
      <BugReportButton />
      {authOpen && <AuthModal onClose={() => setAuthOpen(false)} />}
    </div>
  );
}

export default App;
