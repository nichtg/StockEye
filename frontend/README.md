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
share one origin and the auth cookies stay first-party (no CORS setup needed). Start the backend first
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

`api.get<T>(path)`, `api.post`, `api.patch`, `api.delete`. Paths are relative to `/api`. All requests send
cookies; unsafe methods add the `X-CSRF-Token` header from the `se_csrf` cookie. A 401 (outside `/auth/*`)
triggers one shared `POST /auth/refresh` and a single retry; if that fails the user cache is cleared and the
route guard sends the user to `/login?next=...`. Failures throw `ApiError` (`code`, `message`, `status`, `requestId`).

## Analysis UI

- `src/features/search`: top-bar autocomplete (Ctrl/Cmd+K; `focusSearch()` from anywhere).
- `src/features/watchlist`: overview table, sparkline, optimistic add/remove.
- `src/features/chart`: lightweight-charts v5 hero chart. `model.ts`, `tooltip.ts` and `indicators.ts` are pure and unit-tested; `PriceChart.tsx` owns the canvas.
- `src/features/stock`: header, Technical and Macro tabs.
- `scripts/screenshots.mjs`, `scripts/interactions.mjs`: Playwright walkthroughs against the local stack (output in `screenshots/`).
