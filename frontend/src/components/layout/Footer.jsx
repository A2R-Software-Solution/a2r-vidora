import SiteLink from "../common/SiteLink";
import { siteDetails } from "../../content/siteDetails";
import "./Footer.css";

const linkGroups = [
  {
    title: "Explore",
    links: [
      { href: "/about", label: "About Vidora" },
      { href: "/how-it-works", label: "How it works" },
    ],
  },
  {
    title: "Help & legal",
    links: [
      { href: "/contact", label: "Contact us" },
      { href: "/privacy", label: "Privacy Policy" },
      { href: "/terms", label: "Terms of Use" },
    ],
  },
];

export default function Footer({ currentPath }) {
  return (
    <footer className="site-footer">
      <div className="site-footer-main">
        <div className="site-footer-intro">
          <SiteLink href="/" className="site-footer-brand" aria-label="Vidora AI home">
            <span className="site-footer-mark" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" focusable="false">
                <path d="M8 5v14l11-7-11-7Z" fill="currentColor" />
              </svg>
            </span>
            <span>Vidora <span className="site-footer-ai">AI</span></span>
          </SiteLink>
          <p>Less searching. More understanding.</p>
          <p className="site-footer-description">
            Explore your YouTube videos with summaries, questions, and answers
            you can trace back to the moment.
          </p>
        </div>

        {linkGroups.map(({ title, links }) => (
          <nav className="site-footer-links" aria-label={`Footer ${title}`} key={title}>
            <h2>{title}</h2>
            <ul>
              {links.map(({ href, label }) => (
                <li key={href}>
                  <SiteLink href={href} aria-current={currentPath === href ? "page" : undefined}>
                    {label}
                  </SiteLink>
                </li>
              ))}
            </ul>
          </nav>
        ))}
      </div>

      <div className="site-footer-bottom">
        <div className="site-footer-company">
          <p>
            A product of{" "}
            <a
              href={siteDetails.companyUrl}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="A2R Software Solutions (opens in a new tab)"
            >
              {siteDetails.company}
              <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" focusable="false">
                <path d="M4 12 12 4M4 4h8v8" />
              </svg>
            </a>
          </p>
          <a className="site-footer-email" href={`mailto:${siteDetails.supportEmail}`}>
            {siteDetails.supportEmail}
          </a>
        </div>
        <p className="site-footer-copyright">
          &copy; {new Date().getFullYear()} {siteDetails.company}.
        </p>
      </div>
    </footer>
  );
}
