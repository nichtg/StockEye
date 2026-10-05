# StockEye frontend

Vite, React 19, TypeScript (strict), MUI v7, TanStack Query v5 and React Router v7 (declarative mode).
Fonts are self-hosted (IBM Plex Sans via `@fontsource`), so nothing is loaded from a third-party CDN.

## Setup

Requires Node 22 or newer (developed on Node 24).

```bash
cd frontend
npm ci
npm run dev        # http://localhost:5173
```

The dev server proxies `/api` to the FastAPI backend at `http://127.0.0.1:8000`, so the app and the API
share one origin (no CORS setup needed). Start the backend first
(see `backend/`). With the backend down, the app still renders and shows an error state with a retry button.

## Scripts

| Script              | What it does                                                    |
| ------------------- | --------------------------------------------------------------- |
| `npm run dev`       | Vite dev server with the `/api` proxy                           |
| `npm run build`     | Typecheck (`tsc -b`) then production build                      |
| `npm run preview`   | Serve the production build locally                              |
| `npm run lint`      | ESLint (typescript-eslint strict, react-hooks, jsx-a11y)        |
| `npm run typecheck` | `tsc -b --noEmit` across both project configs                   |
| `npm test`          | Vitest (watch mode; add `-- --run` for CI)                      |
| `npm run format`    | Prettier                                                        |
| `npm run gen:api`   | Regenerate `src/api/schema.d.ts` from `../backend/openapi.json` |

## Layout

- `src/api/`: typed fetch client (`client.ts`), `ApiError`, `schema.d.ts` is generated from the backend OpenAPI (`npm run gen:api`); `types.ts` aliases it.
- `src/theme/`: tokens, `createAppTheme(mode)`, `ColorModeProvider`. Tokens are exposed as CSS variables
  (`--mui-palette-ink`, `--mui-palette-line`, ... and the short aliases `--se-ink`, `--se-up`, ...).
- `src/components/`: app shell, `Term` (jargon tooltip), shared states.
- `src/glossary.ts`: typed glossary; `<Term id="rsi">` is checked at compile time.
- `src/features/auth`, `src/features/admin`: feature code. `src/pages/`: route components.

## API client

`api.get<T>(path)`, `api.post`, `api.patch`, `api.delete`. Paths are relative to the API base URL
(`VITE_API_BASE_URL`, default `/api`). Requests carry `Authorization: Bearer <access token>` and never send
ambient credentials. `src/api/tokens.ts` owns the tokens: the access token is held in memory, the rotating
refresh token in `localStorage`. A 401 (outside `/auth/*`) triggers one `POST /auth/refresh` and a single retry;
the refresh runs under the Web Lock `stockeye-refresh` and re-reads the stored token inside it, so tabs never
re-send a rotated token. Web Locks exist only in secure contexts (https or localhost), so the plain-http LAN docker stack and browsers without `navigator.locks` only dedupe within a tab. Refreshes time out (10 s request, 15 s lock wait) and keep the session on a timeout; after storing a rotated token the lock holder waits 250 ms so the storage write reaches other tabs first. Logout runs under the same lock. The stored value also carries the user id: if another tab signs in as someone else, this tab clears itself and reloads. If the refresh is
rejected the user cache is cleared and the route guard sends the user to `/login?next=...`; signing out in one
tab signs out the others. Failures throw `ApiError` (`code`, `message`, `status`, `requestId`).

## Configuration and GitHub Pages build

| Variable            | Default | Meaning                                                                           |
| ------------------- | ------- | --------------------------------------------------------------------------------- |
| `VITE_API_BASE_URL` | `/api`  | API location: a same-origin path, or an absolute URL for a cross-site API         |
| `VITE_BASE_PATH`    | `/`     | Path the app is served under (Vite `base` and router basename), e.g. `/StockEye/` |

```bash
VITE_API_BASE_URL=https://api.example.com/api VITE_BASE_PATH=/StockEye/ npm run build
```

The build emits no source maps, copies `index.html` to `404.html` (so deep links work on Pages), and writes a
`<meta>` Content-Security-Policy whose `connect-src` is the API origin (`'self'` for a relative URL). Pages cannot
send `frame-ancestors`, so `index.html` hides the page until the bundle confirms it is the top-level window
(`src/lib/frameGate.ts`); a framed copy neither renders nor calls the API. `localStorage` is per origin, so the `github.io` origin (`https://nichtg.github.io`) must host no other Pages site: never enable Pages on another repository of that account. `VITE_API_BASE_URL` is validated at build time: a path starting with `/`, or an absolute `https:` URL without credentials, query or fragment (`http:` only for localhost or 127.0.0.1). The plugins live in `build-tools/plugins.ts`.

## Analysis UI

- `src/features/search`: top-bar autocomplete (Ctrl/Cmd+K; `focusSearch()` from anywhere).
- `src/features/watchlist`: overview table, sparkline, optimistic add/remove.
- `src/features/chart`: lightweight-charts v5 hero chart. `model.ts`, `tooltip.ts` and `indicators.ts` are pure and unit-tested; `PriceChart.tsx` owns the canvas.
- `src/features/stock`: header, Technical and Macro tabs.
- `scripts/screenshots.mjs`, `scripts/interactions.mjs`: Playwright walkthroughs against the local stack (output in `screenshots/`).
