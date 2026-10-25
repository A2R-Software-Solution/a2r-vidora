import { lazy, Suspense, useEffect, useLayoutEffect, useState, useSyncExternalStore } from "react";
import { onAuthStateChanged } from "firebase/auth";
import { auth } from "./firebase";
import AuthModal from "./components/auth/AuthModal";
import Navbar from "./components/layout/Navbar";
import Footer from "./components/layout/Footer";
import LandingPage from "./pages/LandingPage";
import ProductHome from "./pages/ProductHome";
import HowItWorksSection from "./components/landing/HowItWorksSection";
import WorkspacePage from "./pages/WorkspacePage";
import PublicPage from "./pages/PublicPage";
import PricingPage from "./pages/PricingPage";
import SongMergerPage from "./pages/SongMergerPage";
import { pricingMeta } from "./utils/pricing";
import { songMergerMeta } from "./utils/audioMerge";
import { refreshCredits } from "./hooks/useCredits";
import { publicPages } from "./content/publicPages";
import { getCurrentPath, subscribeToNavigation } from "./utils/siteNavigation";
import SpotlightGlow from "./components/common/SpotlightGlow";
import BugReportButton from "./components/common/BugReportButton";
import "./App.css";

// Loaded only on /admin so admin code stays out of the main bundle.
const AdminPage = lazy(() => import("./pages/AdminPage"));

function App() {
  const path = useSyncExternalStore(subscribeToNavigation, getCurrentPath);
  const isHome = path === "/";
  const isPricing = path === "/pricing";
  const isAdmin = path === "/admin";
  const isMerger = path === "/song-merger";
  const isTool = path === "/reels" || path === "/analyze";
  const mode = path === "/reels" ? "reels" : "analyze";
  const [video, setVideo] = useState(null);
  const [user, setUser] = useState(null);
  const [authOpen, setAuthOpen] = useState(false);
  const [hasVisitedHome, setHasVisitedHome] = useState(isTool);
  // Mount on first home visit, then retain drafts and the workspace while reading.
  if (isTool && !hasVisitedHome) setHasVisitedHome(true);
  const publicPage = isPricing ? pricingMeta : isMerger ? songMergerMeta : Object.hasOwn(publicPages, path) ? publicPages[path] : null;

  useEffect(() => onAuthStateChanged(auth, setUser), []);

  // The wallet changes with the account (guest ↔ signed in).
  useEffect(() => { void refreshCredits(); }, [user]);

  useEffect(() => {
    const previous = window.history.scrollRestoration;
    window.history.scrollRestoration = "manual";
    return () => { window.history.scrollRestoration = previous; };
  }, []);

  useLayoutEffect(() => {
    document.title = isHome ? "Vidora AI — Understand your videos" : `${isAdmin ? "Admin" : publicPage?.label || "Page not found"} | Vidora AI`;
    document.querySelector('meta[name="description"]')?.setAttribute("content",
      publicPage?.description || "Explore YouTube videos with AI summaries and timestamp-linked questions. A product of A2R Software Solutions.");
    const frame = window.requestAnimationFrame(() => {
      if (isTool) document.title = `${mode === "reels" ? "Create Reel" : "Analyze Video"} | Vidora AI`;
      const heading = document.querySelector(isHome ? ".product-home h1" : isTool ? ".home-content h1" : ".public-page h1");
      heading?.setAttribute("tabindex", "-1");
      heading?.focus({ preventScroll: true });
      const anchor = window.location.hash && document.getElementById(window.location.hash.slice(1));
      if (anchor) anchor.scrollIntoView();
      else window.scrollTo({ top: window.history.state?.vidoraScroll || 0, behavior: "instant" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [path, isHome, isAdmin, isTool, mode, publicPage]);

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
      <Navbar currentPath={path} user={user} onAuth={() => setAuthOpen(true)} />
      <main id="main-content" className="site-main" tabIndex={-1}>
        {isHome && <ProductHome />}
        {hasVisitedHome && <div className="home-content" hidden={!isTool} inert={!isTool}>
          <LandingPage onAnalyzed={setVideo} compact={!!video} active={isTool} mode={mode} />
          {video && <WorkspacePage key={video.id} video={video} active={isTool} mode={mode} onSignIn={() => setAuthOpen(true)} signedIn={!!user} />}
          {mode === "analyze" && <HowItWorksSection />}
        </div>}
        {isPricing && <PricingPage signedIn={!!user} onSignIn={() => setAuthOpen(true)} />}
        {isMerger && <SongMergerPage signedIn={!!user} />}
        {isAdmin && <Suspense fallback={null}><AdminPage user={user} onSignIn={() => setAuthOpen(true)} /></Suspense>}
        {!isHome && !isTool && !isPricing && !isMerger && !isAdmin && <PublicPage page={publicPage} hasAnalysis={!!video} />}
      </main>
      <Footer currentPath={path} />
      <BugReportButton />
      {authOpen && <AuthModal onClose={() => setAuthOpen(false)} />}
    </div>
  );
}

export default App;
