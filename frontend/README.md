# React + Vite

## Public pages and footer

The footer links to `/about`, `/how-it-works`, `/privacy`, `/terms`, and `/contact`.
These pages are public and do not require sign-in. Page content lives in
`src/content/publicPages.jsx`; company details and the policy revision date are
in `src/content/siteDetails.js`. Update the privacy text when integrations or
data-handling practices change.

`vercel.json` enables direct links and refreshes on these routes. Deploy this
directory as the Vercel project root. Internal navigation keeps the current
account and analysis in memory; refreshing still relies on the existing
resume-analysis flow.

To run the local browser check on Windows, start a server with
`node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5175`, then run
`node scripts/check-public-pages.mjs` in a second terminal. It uses headless
Chrome with a fresh temporary profile and blocks all non-local page requests.
Set `CHROME_PATH` if Chrome is installed elsewhere. Screenshots are saved in
the temporary profile directory printed by the script.

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and [`typescript-eslint`](https://typescript-eslint.io) in your project.
