// Runs after `vite build` + the SSR build: writes static HTML per public page, a sitemap
// and llms.txt.
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

const SITE = "https://vidoraa.com";
const dist = resolve("dist");
const { paths, renderPath, renderHome, homeMeta, pageMeta, pageSections, structuredData } =
  await import(pathToFileURL(resolve(".prerender/prerender.js")).href);
const template = readFileSync(resolve(dist, "index.html"), "utf8");
const esc = (s) => s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
// "<" escaped so text in the data can never close the script tag.
const jsonLd = (data) => JSON.stringify(data).replace(/</g, "\\u003c");

function build({ title, description, path, body }) {
  const url = SITE + (path === "/" ? "/" : path);
  return template
    .replace(/<title>.*?<\/title>/, `<title>${esc(title)}</title>`)
    .replace(/(<meta name="description" content=")[^"]*(")/, `$1${esc(description)}$2`)
    .replace("</head>", `  <link rel="canonical" href="${url}" />\n    <meta property="og:title" content="${esc(title)}" />\n    <meta property="og:description" content="${esc(description)}" />\n    <meta property="og:url" content="${url}" />\n    <script type="application/ld+json">${jsonLd(structuredData(path))}</script>\n  </head>`)
    // main.jsx hydrates only when this matches the visited path.
    .replace('<div id="root"></div>', `<div id="root" data-prerendered="${path}">${body}</div>`);
}

writeFileSync(resolve(dist, "index.html"), build({ ...homeMeta, path: "/", body: renderHome() }));

for (const path of paths) {
  const { page, html } = renderPath(path);
  const dir = resolve(dist, path.slice(1));
  mkdirSync(dir, { recursive: true });
  writeFileSync(resolve(dir, "index.html"), build({
    title: `${page.label} | Vidora AI`, description: page.description, path, body: html,
  }));
}

const today = new Date().toISOString().slice(0, 10);
const urls = ["/", ...paths].map((p) => `  <url><loc>${SITE}${p === "/" ? "/" : p}</loc><lastmod>${today}</lastmod></url>`);
writeFileSync(resolve(dist, "sitemap.xml"), `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.join("\n")}\n</urlset>\n`);

// llms.txt (llmstxt.org): a plain-text map of the site for AI assistants.
const link = (path) => `- [${pageMeta(path).label}](${SITE}${path}): ${pageMeta(path).description}`;
const guides = paths.filter((p) => p.startsWith("/guides/"));
writeFileSync(resolve(dist, "llms.txt"), [
  "# Vidora AI",
  "",
  `> ${homeMeta.description}`,
  "",
  "Vidora AI is a web app by A2R Software Solutions. It transcribes the speech in a public YouTube video, writes a summary, and answers questions about the video with timestamp links to the moment that supports each answer.",
  "",
  "## Pages",
  "",
  ...paths.filter((p) => !p.startsWith("/guides/")).map(link),
  "",
  "## Guides",
  "",
  ...guides.map(link),
  "",
  "## FAQ",
  "",
  ...pageSections("/faq").flatMap(({ title, text }) => [`### ${title}`, "", text, ""]),
].join("\n"));

console.log(`Prerendered ${paths.length + 1} pages, sitemap.xml and llms.txt`);
