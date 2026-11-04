// Build-time entry: renders public pages to static HTML so crawlers see real content.
// It renders the same <App /> the browser hydrates, so the markup must match exactly.
import { renderToString } from "react-dom/server";
import App from "./App";
import { pricingMeta } from "./utils/pricing";
import { songMergerMeta } from "./utils/audioMerge";
import { downloaderMeta } from "./utils/mediaDownload";
import { publicPages } from "./content/publicPages";
import { setPrerenderPath } from "./utils/siteNavigation";

const toolPages = { "/pricing": pricingMeta, "/song-merger": songMergerMeta, "/downloader": downloaderMeta };

export const paths = [...Object.keys(publicPages), ...Object.keys(toolPages)];

export function renderPath(path) {
  setPrerenderPath(path);
  return {
    page: toolPages[path] || publicPages[path],
    html: renderToString(<App />),
  };
}

export function renderHome() {
  setPrerenderPath("/");
  return renderToString(<App />);
}
