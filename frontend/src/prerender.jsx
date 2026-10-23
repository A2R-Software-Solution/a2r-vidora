// Build-time entry: renders public pages to static HTML so crawlers see real content.
import { renderToStaticMarkup } from "react-dom/server";
import PublicPage from "./pages/PublicPage";
import Footer from "./components/layout/Footer";
import ProductHome from "./pages/ProductHome";
import PricingPage from "./pages/PricingPage";
import { pricingMeta } from "./utils/pricing";
import { publicPages } from "./content/publicPages";

export const paths = [...Object.keys(publicPages), "/pricing"];

const pageTitle = (path) => (path === "/pricing" ? "Pricing" : publicPages[path].title);

export function renderPath(path) {
  const isPricing = path === "/pricing";
  const page = isPricing ? pricingMeta : publicPages[path];
  return {
    page,
    html: renderToStaticMarkup(
      <div className="page page--reading">
        <main id="main-content" className="site-main">{isPricing ? <PricingPage /> : <PublicPage page={page} />}</main>
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
              {paths.map((path) => <li key={path}><a href={path}>{pageTitle(path)}</a></li>)}
            </ul>
          </nav>
        </article>
      </main>
      <Footer currentPath="/" />
    </div>,
  );
}
