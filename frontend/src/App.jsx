import { useState } from "react";
import Navbar from "./components/layout/Navbar";
import LandingPage from "./pages/LandingPage";
import WorkspacePage from "./pages/WorkspacePage";
import "./App.css";

function App() {
  const [video, setVideo] = useState(null);

  return (
    <div className="page">
      <Navbar onHome={() => setVideo(null)} />
      <LandingPage onAnalyzed={setVideo} compact={!!video} />
      {video && <WorkspacePage video={video} />}
    </div>
  );
}

export default App;