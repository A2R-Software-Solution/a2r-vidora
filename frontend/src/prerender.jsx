// Build-time entry: renders public pages to static HTML so crawlers see real content.
import { renderToStaticMarkup } from "react-dom/server";
import PublicPage from "./pages/PublicPage";
import Footer from "./components/layout/Footer";
import { publicPages } from "./content/publicPages";

export const paths = Object.keys(publicPages);

export function renderPath(path) {
  const page = publicPages[path];
  return {
    page,
    html: renderToStaticMarkup(
      <div className="page page--reading">
        <main id="main-content" className="site-main"><PublicPage page={page} /></main>
        <Footer currentPath={path} />
      </div>,
    ),
  };
}

export function renderHome() {
  return renderToStaticMarkup(
    <div className="page">
      <main id="main-content" className="site-main">
        <article className="public-page">
          <header className="public-header">
            <p className="public-eyebrow">AI-powered video intelligence</p>
            <h1>Understand any video with AI, instantly.</h1>
            <p className="public-intro">Paste a YouTube video and ask questions, find exact moments, and get summaries. Vidora AI turns the spoken content of a video into a searchable conversation with timestamp links back to the source.</p>
          </header>
          <nav aria-label="Site pages">
            <ul>
              {paths.map((path) => <li key={path}><a href={path}>{publicPages[path].title}</a></li>)}
            </ul>
          </nav>
        </article>
      </main>
      <Footer currentPath="/" />
    </div>,
  );
}
