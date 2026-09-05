# React + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and [`typescript-eslint`](https://typescript-eslint.io) in your project.


## AI transparency

The frontend includes pre-submission processing notices, AI output labels, source excerpt review with video seeking, expiry display, governance-error handling, and downloadable issue reports. The latter are local downloads, not submissions to a support service. Source excerpts are available on new answer responses; historical responses do not reconstruct them.

Run checks from `frontend/`:

```sh
npm install
npm run build
npm run lint
npm test
```

UI tests use the existing Vite and React dependencies with Node's test runner. They verify server-rendered disclosure/error/source states, not live browser playback or external AI quality. Backend source-response tests run with the governance suite in `functions/tests`.

See [AI risk management](../docs/ai-risk-management.md) for limitations and deployment responsibilities.
