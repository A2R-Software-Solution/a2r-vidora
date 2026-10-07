// Build-time entry: renders public pages to static HTML so crawlers see real content.
import { renderToStaticMarkup } from "react-dom/server";
import PublicPage from "./pages/PublicPage";
import Footer from "./components/layout/Footer";
import ProductHome from "./pages/ProductHome";
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
        <ProductHome />
        <article className="public-page">
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
