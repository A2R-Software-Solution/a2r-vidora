import SiteLink from "../components/common/SiteLink";
import { siteDetails } from "../content/siteDetails";
import "./PublicPage.css";

export default function PublicPage({ page, hasAnalysis }) {
  if (!page) {
    return (
      <article className="public-page public-not-found">
        <p className="public-eyebrow">404 / Page not found</p>
        <h1>This page has moved off screen.</h1>
        <p>Check the address, or head back to Vidora to explore a video.</p>
        <SiteLink className="public-action" href="/">Back to Vidora</SiteLink>
      </article>
    );
  }

  return (
    <article className="public-page">
      <SiteLink className="public-back" href="/">
        <span aria-hidden="true">←</span> {hasAnalysis ? "Back to your analysis" : "Back to Vidora"}
      </SiteLink>
      <header className="public-header">
        <p className="public-eyebrow">{page.eyebrow}</p>
        <h1>{page.title}</h1>
        <p className="public-intro">{page.intro}</p>
        {page.updated && <p className="public-updated">Last updated: {siteDetails.policyUpdated}</p>}
      </header>
      <div className="public-layout">
        <aside className="public-sidebar">
          <nav className="public-toc" aria-label="On this page">
            <h2>On this page</h2>
            <ol>
              {page.sections.map((section) => (
                <li key={section.id}><a href={`#${section.id}`}>{section.title}</a></li>
              ))}
            </ol>
          </nav>
          <p className="public-help">Need a hand?<br /><SiteLink href="/contact">Talk to our team <span aria-hidden="true">↗</span></SiteLink></p>
        </aside>
        <div className="public-body">
          {page.sections.map((section) => (
            <section key={section.id} id={section.id} aria-labelledby={`${section.id}-title`}>
              <h2 id={`${section.id}-title`}>{section.title}</h2>
              {section.content}
            </section>
          ))}
        </div>
      </div>
    </article>
  );
}
