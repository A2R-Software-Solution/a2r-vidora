import { useEffect, useLayoutEffect, useState, useSyncExternalStore } from "react";
import { onAuthStateChanged } from "firebase/auth";
import { auth } from "./firebase";
import AuthModal from "./components/auth/AuthModal";
import Navbar from "./components/layout/Navbar";
import Footer from "./components/layout/Footer";
import LandingPage from "./pages/LandingPage";
import HowItWorksSection from "./components/landing/HowItWorksSection";
import WorkspacePage from "./pages/WorkspacePage";
import PublicPage from "./pages/PublicPage";
import { publicPages } from "./content/publicPages";
import { getCurrentPath, subscribeToNavigation } from "./utils/siteNavigation";
import SpotlightGlow from "./components/common/SpotlightGlow";
import BugReportButton from "./components/common/BugReportButton";
import "./App.css";

function App() {
  const path = useSyncExternalStore(subscribeToNavigation, getCurrentPath);
  const isHome = path === "/";
  const [video, setVideo] = useState(null);
  const [user, setUser] = useState(null);
  const [authOpen, setAuthOpen] = useState(false);
  const [hasVisitedHome, setHasVisitedHome] = useState(isHome);
  // Mount on first home visit, then retain drafts and the workspace while reading.
  if (isHome && !hasVisitedHome) setHasVisitedHome(true);
  const publicPage = Object.hasOwn(publicPages, path) ? publicPages[path] : null;

  useEffect(() => onAuthStateChanged(auth, setUser), []);

  useEffect(() => {
    const previous = window.history.scrollRestoration;
    window.history.scrollRestoration = "manual";
    return () => { window.history.scrollRestoration = previous; };
  }, []);

  useLayoutEffect(() => {
    document.title = isHome ? "Vidora AI — Understand your videos" : `${publicPage?.label || "Page not found"} | Vidora AI`;
    document.querySelector('meta[name="description"]')?.setAttribute("content",
      publicPage?.description || "Explore YouTube videos with AI summaries and timestamp-linked questions. A product of A2R Software Solutions.");
    const frame = window.requestAnimationFrame(() => {
      const heading = document.querySelector(isHome ? ".home-content h1" : ".public-page h1");
      heading?.setAttribute("tabindex", "-1");
      heading?.focus({ preventScroll: true });
      const anchor = window.location.hash && document.getElementById(window.location.hash.slice(1));
      if (anchor) anchor.scrollIntoView();
      else window.scrollTo({ top: window.history.state?.vidoraScroll || 0, behavior: "instant" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [path, isHome, publicPage]);

  return (
    <div className={`page${isHome ? "" : " page--reading"}`}>
      <a className="skip-link" href="#main-content">Skip to content</a>
      <div className="floating-bubbles" aria-hidden="true">
        <span className="bubble b1"></span>
        <span className="bubble b2"></span>
        <span className="bubble b3"></span>
        <span className="bubble b4"></span>
      </div>
      <SpotlightGlow />
      <Navbar onHome={() => { if (isHome) setVideo(null); }} user={user} onAuth={() => setAuthOpen(true)} />
      <main id="main-content" className="site-main" tabIndex={-1}>
        {hasVisitedHome && <div className="home-content" hidden={!isHome} inert={!isHome}>
          <LandingPage onAnalyzed={setVideo} compact={!!video} active={isHome} />
          {!video && <HowItWorksSection />}
          {video && <WorkspacePage key={video.id} video={video} active={isHome} />}
          {video && <HowItWorksSection />}
        </div>}
        {!isHome && <PublicPage page={publicPage} hasAnalysis={!!video} />}
      </main>
      <Footer currentPath={path} />
      <BugReportButton />
      {authOpen && <AuthModal onClose={() => setAuthOpen(false)} />}
    </div>
  );
}

export default App;
