// Runs after `vite build` + the SSR build: writes static HTML per public page and a sitemap.
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

const SITE = "https://vidoraa.com";
const dist = resolve("dist");
const { paths, renderPath, renderHome } = await import(pathToFileURL(resolve(".prerender/prerender.js")).href);
const template = readFileSync(resolve(dist, "index.html"), "utf8");
const esc = (s) => s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

function build({ title, description, path, body }) {
  const url = SITE + (path === "/" ? "/" : path);
  return template
    .replace(/<title>.*?<\/title>/, `<title>${esc(title)}</title>`)
    .replace(/(<meta name="description" content=")[^"]*(")/, `$1${esc(description)}$2`)
    .replace("</head>", `  <link rel="canonical" href="${url}" />\n    <meta property="og:title" content="${esc(title)}" />\n    <meta property="og:description" content="${esc(description)}" />\n    <meta property="og:url" content="${url}" />\n  </head>`)
    .replace('<div id="root"></div>', `<div id="root">${body}</div>`);
}

writeFileSync(resolve(dist, "index.html"), build({
  title: "Vidora AI — Understand your videos",
  description: "Explore YouTube videos with AI summaries and timestamp-linked questions. A product of A2R Software Solutions.",
  path: "/",
  body: renderHome(),
}));

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
console.log(`Prerendered ${paths.length + 1} pages and sitemap.xml`);
