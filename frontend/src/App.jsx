import { useState } from "react";
import Navbar from "./components/layout/Navbar";
import LandingPage from "./pages/LandingPage";
import WorkspacePage from "./pages/WorkspacePage";
import "./App.css";

function App() {
  const [video, setVideo] = useState(null);

  return (
    <div className="page">
      <div className="floating-bubbles" aria-hidden="true">
        <span className="bubble b1"></span>
        <span className="bubble b2"></span>
        <span className="bubble b3"></span>
        <span className="bubble b4"></span>
      </div>
      <Navbar onHome={() => setVideo(null)} />
      <LandingPage onAnalyzed={setVideo} compact={!!video} />
      {video && <WorkspacePage video={video} />}
    </div>
  );
}

export default App;