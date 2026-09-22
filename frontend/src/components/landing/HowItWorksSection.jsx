import SiteLink from "../common/SiteLink";
import { publicPages } from "../../content/publicPages";
import "../../pages/PublicPage.css";
import "./HowItWorksSection.css";

export default function HowItWorksSection() {
  const page = publicPages["/how-it-works"];

  return (
    <article className="public-page embedded-how-it-works" aria-labelledby="how-it-works-title">
      <header className="public-header">
        <p className="public-eyebrow">{page.eyebrow}</p>
        <h2 id="how-it-works-title">{page.title}</h2>
        <p className="public-intro">{page.intro}</p>
      </header>
      <div className="public-layout">
        <aside className="public-sidebar">
          <nav className="public-toc" aria-label="How it works sections">
            <h2>On this page</h2>
            <ol>{page.sections.map((section) => <li key={section.id}><a href={`#${section.id}`}>{section.title}</a></li>)}</ol>
          </nav>
          <p className="public-help">Need a hand?<br /><SiteLink href="/contact">Talk to our team <span aria-hidden="true">→</span></SiteLink></p>
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
