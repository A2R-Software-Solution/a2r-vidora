import { useState, useEffect } from "react";
import Navbar from "./components/layout/Navbar";
import LandingPage from "./pages/LandingPage";
import WorkspacePage from "./pages/WorkspacePage";
import { useVideoAnalyze } from "./hooks/useVideoAnalyze";
import "./App.css";

function App() {
  const [video, setVideo] = useState(null);
  const { restoreVideo } = useVideoAnalyze();

  // Page load hote hi localStorage me saved video_id check karo.
  // Agar mil jaye toh seedha Workspace pe le jao (restore).
  useEffect(() => {
    const restoreOnLoad = async () => {
      const restoredVideo = await restoreVideo();
      if (restoredVideo) {
        setVideo(restoredVideo);
      }
    };

    restoreOnLoad();
    // Sirf mount hone par ek baar chalana hai, isliye dependency array empty.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="page">
      <Navbar />
      {video ? (
        <WorkspacePage video={video} />
      ) : (
        <LandingPage onAnalyzed={setVideo} />
      )}
    </div>
  );
}

export default App;