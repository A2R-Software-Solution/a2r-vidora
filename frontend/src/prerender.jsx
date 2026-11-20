// Build-time entry: renders public pages to static HTML so crawlers see real content.
// It renders the same <App /> the browser hydrates, so the markup must match exactly.
import { renderToString, renderToStaticMarkup } from "react-dom/server";
import App from "./App";
import { pricingMeta, FALLBACK_PACKS } from "./utils/pricing";
import { songMergerMeta } from "./utils/audioMerge";
import { downloaderMeta } from "./utils/mediaDownload";
import { publicPages } from "./content/publicPages";
import { siteDetails, homeMeta } from "./content/siteDetails";
import { setPrerenderPath } from "./utils/siteNavigation";

const SITE = "https://vidoraa.com";
const toolPages = { "/pricing": pricingMeta, "/song-merger": songMergerMeta, "/downloader": downloaderMeta };

export const paths = [...Object.keys(publicPages), ...Object.keys(toolPages)];
export { homeMeta };

export function pageMeta(path) {
  return toolPages[path] || publicPages[path];
}

export function renderPath(path) {
  setPrerenderPath(path);
  return { page: pageMeta(path), html: renderToString(<App />) };
}

export function renderHome() {
  setPrerenderPath("/");
  return renderToString(<App />);
}

const entities = { amp: "&", lt: "<", gt: ">", quot: '"', "#x27": "'", "#39": "'", nbsp: " " };

// A page's sections as plain text, for structured data and llms.txt.
export function pageSections(path) {
  return (publicPages[path]?.sections || []).map(({ title, content }) => ({
    title,
    text: renderToStaticMarkup(content)
      .replace(/<\/(p|li)>/g, " ").replace(/<[^>]+>/g, "")
      .replace(/&(#?\w+);/g, (match, name) => entities[name] ?? match)
      .replace(/\s+/g, " ").trim(),
  }));
}

const organization = {
  "@type": "Organization",
  "@id": `${SITE}/#organization`,
  name: siteDetails.company,
  url: siteDetails.companyUrl,
};

const website = {
  "@type": "WebSite",
  "@id": `${SITE}/#website`,
  name: "Vidora AI",
  alternateName: ["VidoraAI", "Vidora"],
  url: `${SITE}/`,
  inLanguage: "en",
  publisher: { "@id": organization["@id"] },
};

const application = {
  "@type": "WebApplication",
  "@id": `${SITE}/#app`,
  name: "Vidora AI",
  url: `${SITE}/`,
  description: homeMeta.description,
  applicationCategory: "EducationalApplication",
  operatingSystem: "Web",
  publisher: { "@id": organization["@id"] },
  offers: [
    { "@type": "Offer", name: "Free monthly credits", price: "0", priceCurrency: "USD" },
    ...FALLBACK_PACKS.map((pack) => ({
      "@type": "Offer",
      name: `${pack.credits} credits`,
      price: (pack.amount_cents / 100).toFixed(2),
      priceCurrency: pack.currency,
      url: `${SITE}/pricing`,
    })),
  ],
};

function breadcrumbs(path) {
  const trail = [["Home", "/"]];
  if (path.startsWith("/guides/")) trail.push(["Guides", "/guides"]);
  trail.push([pageMeta(path).label, path]);
  return {
    "@type": "BreadcrumbList",
    itemListElement: trail.map(([name, href], i) => ({
      "@type": "ListItem", position: i + 1, name, item: SITE + href,
    })),
  };
}

// schema.org JSON-LD for a page, so search engines and AI answers can read who runs
// the site, what the product is, and the page's facts without guessing from layout.
export function structuredData(path) {
  if (path === "/") return { "@context": "https://schema.org", "@graph": [organization, website, application] };
  const page = pageMeta(path);
  const graph = [breadcrumbs(path)];
  if (path === "/faq") {
    graph.push({
      "@type": "FAQPage",
      url: SITE + path,
      mainEntity: pageSections(path).map(({ title, text }) => ({
        "@type": "Question", name: title, acceptedAnswer: { "@type": "Answer", text },
      })),
    });
  } else if (path.startsWith("/guides/")) {
    graph.push({
      "@type": "Article",
      headline: page.title,
      description: page.description,
      url: SITE + path,
      mainEntityOfPage: SITE + path,
      inLanguage: "en",
      author: { "@id": organization["@id"] },
      publisher: { "@id": organization["@id"] },
      isPartOf: { "@id": website["@id"] },
    });
  }
  return { "@context": "https://schema.org", "@graph": [...graph, organization, website] };
}
