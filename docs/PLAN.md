# StockEye: build plan and status

> This is the approved build plan, kept in the repo so work can continue in any session. The "Status" section at the end is updated as phases complete.


## Context
You want a production-quality web app that analyzes US and SG (SGX) stocks in two ways:
- **Macro (2-year horizon):** relate news sentiment to the price moves around the time each story came out.
- **Technical (1-week horizon):** candlestick patterns plus standard indicators.

It also needs accounts (login, register, an admin page where the admin cannot see other users' watchlists), a watchlist, a minimal black/white Material UI with light and dark modes, and an event-annotated chart. The backend must use a NoSQL store and fail gracefully. The code is refined with the thermo-nuclear-code-quality-review, improve-codebase-architecture and find-skills skills, then delivered as a private GitHub repo **StockEye** with at least 2 PRs.

`D:\Vibe Coding Projects\StockEye` is empty, so everything is new. Tools available: Node 24, Python 3.14, git, and gh (logged in as `nichtg`). Docker and MongoDB are not installed.

**Your decisions so far:**
- Database: local MongoDB for dev and tests, with Atlas documented for deployment.
- Data: free sources plus optional API keys.
- Sentiment: FinBERT run locally through ONNX.
- Repo: private.

## Tech stack (this goes into the report)
| Layer | Choice | Purpose |
|---|---|---|
| Backend language | Python 3.13 (pinned with **uv**, because wheels for onnxruntime and scipy are safer than on 3.14) | Strong numeric and NLP ecosystem |
| Web framework | FastAPI + Pydantic v2 + pydantic-settings | Typed API, auto-generated OpenAPI (feeds the frontend types), env config |
| Database | MongoDB (local Community Server installed via winget; Atlas through `MONGODB_URI`), accessed with PyMongo's native async client (Motor is deprecated) | Document store for users, watchlists, bars (time-series collection), news, events, cache and quota state |
| Data and math | pandas, numpy, scipy.stats | Indicators, pattern detection, event study, significance tests |
| Sentiment | ProsusAI/finbert exported to ONNX, run with onnxruntime + tokenizers | Local, deterministic scoring of financial headlines |
| HTTP and resilience | httpx, tenacity, a small custom circuit breaker and quota ledger | Timeouts, backoff, rate-limit handling |
| Providers | yfinance (prices, earnings, dividends, splits for US and `.SI` tickers), Yahoo search, Google News RSS (date-windowed), SGX announcements; optional Finnhub, Alpha Vantage, Marketaux | Market data and news |
| Jobs | APScheduler | Nightly refresh of watchlisted tickers, incremental news ingestion |
| Auth | argon2-cffi, PyJWT, slowapi | Password hashing, access and refresh tokens, login rate limiting |
| Backend tooling | ruff, mypy (strict), pytest, pytest-asyncio, respx, hypothesis | Lint, type checks and tests |
| Frontend | React 19 + TypeScript + Vite, MUI (custom monochrome theme), TanStack Query, React Router, TradingView **lightweight-charts** v5, openapi-typescript | UI, data fetching with stale and error states, the candlestick chart with markers and indicator panes, a typed API client |
| Frontend tooling | ESLint, Prettier, Vitest + Testing Library, Playwright | Lint, unit tests, end-to-end tests and screenshots |
| CI and deploy | GitHub Actions (with a MongoDB service container), Dockerfiles plus docker-compose (frontend served by nginx) | CI checks on every PR; deployable images |

## Step 0: load the skills (first thing in execution)
1. Run the three `npx skills use ...` commands you gave, redirect each output to a scratchpad file, and read each file in full. Relative paths resolve from the supporting-files directory each one reports.
2. **find-skills is used throughout the project, not just once.** At the start of every new kind of task, search for a skill that covers it and use any good matches. Expected moments:
   - FastAPI and Python backend
   - MongoDB schema and indexes
   - pytest and Playwright testing
   - chart and data-viz design
   - frontend and UI design (for example a frontend-design or web-design-guidelines skill)
   - accessibility
   - security hardening
   - GitHub Actions CI
   - writing PR descriptions

   Every skill found and applied is listed in the report, along with the step where it was used.
3. Install the tooling: uv, and MongoDB Community via winget (run as a Windows service).

## Repo layout
```
StockEye/
  backend/app/
    main.py, config.py, cli.py              # app factory, settings, `create-admin` command
    api/        auth.py, me.py, admin.py, watchlist.py, stocks.py, errors.py
    auth/       passwords.py, tokens.py, deps.py   # current_user, require_admin, CSRF
    domain/technical/  indicators.py, candlesticks.py, reliability.py, outlook.py   # pure, no I/O
    domain/macro/      alignment.py, event_study.py, sentiment_stats.py, summary.py # pure, no I/O
    sentiment/  scorer.py (Protocol), finbert_onnx.py
    providers/  base.py, resilience.py (retry, breaker, quota), yahoo.py, google_news.py, sgx.py, finnhub.py, alphavantage.py, marketaux.py
    services/   market_data.py, news.py, analysis.py   # cache-first, stale fallback, orchestration
    repositories/ users.py, watchlists.py, bars.py, news.py, events.py, cache.py, quotas.py
    jobs/       scheduler.py
  backend/tests/  unit/ (domain fixtures and property tests), integration/ (API on a test Mongo DB), providers/ (respx failure cases)
  frontend/src/  theme/, api/ (generated types + client), components/ (Term, PriceChart, IndicatorToggles, WatchlistButton…), pages/, glossary.ts
  docs/REPORT.md, docs/ARCHITECTURE.md
  .github/workflows/ backend.yml, frontend.yml
```
Architecture rule: `domain/` is pure, with no I/O and nothing imported from `providers` or `repositories`. Services are the only layer that combines providers, repositories and domain code. An import-linter contract enforces this.

## Backend design

### Data model (MongoDB)
- `users`: email (unique), argon2 hash, role (`user` or `admin`), status, timestamps.
- `refresh_tokens`: stored hashed, rotated on use, TTL index.
- `watchlists`: `{owner_id, symbols[]}`. **Only reachable through `WatchlistRepository`, whose every method requires `owner_id` taken from the authenticated principal.** The admin router never imports it; an import-linter contract and a test enforce this. The admin API returns no watchlist fields at all.
- `price_bars`: time-series collection (symbol, interval, ts).
- `corporate_events`: earnings, dividends and splits.
- `news_articles`: deduplicated by canonical-URL hash plus normalized-title hash; fields are symbols, source, published_at in UTC, sentiment {pos, neg, neu, score}, model version.
- `analysis_cache`: TTL index.
- `provider_quota`: daily and per-minute counters per provider.

### Graceful failure (applies to every provider)
- Every external call has an explicit httpx timeout and a retry with exponential backoff and jitter, but only on transient errors: 5xx, timeouts, and 429 (which honours `Retry-After`).
- A circuit breaker per provider opens after N consecutive failures and half-opens after a cool-down.
- A quota ledger stored in Mongo blocks calls before a free-tier limit is hit, so it is never discovered by failing. **Quota visibility:**
  - Logs (structured, with provider name, used/limit and reset time):
    - one WARNING when a provider passes 80% of its quota
    - one ERROR when it reaches the limit and calls are blocked
    - one INFO when the quota resets
    - real 429 responses from providers are logged as ERROR too
  - The admin page gets a **Data providers** panel (`GET /admin/providers`) listing each provider with:
    - quota used versus limit
    - the reset time
    - circuit-breaker state
    - the last error with its timestamp

    A prominent alert banner appears at the top of the admin page whenever any provider is at or above 80%, or is blocked. The panel contains no user data.
- Reads are cache-first. If a refresh fails, the cached data is served with `stale: true` and its `as_of` timestamp.
- Each analysis response carries `data_status: {prices, news, events}` set to `ok`, `stale`, `partial` or `unavailable`, plus a human-readable reason. The UI turns this into a subtle banner instead of crashing.
- Provider fallback chain: news from Finnhub → Marketaux → Alpha Vantage, when their keys are set, then always Google News RSS. Provider responses are validated with Pydantic, so malformed payloads are logged and skipped. Logs are structured and tagged with a request id.
- One global exception handler returns a consistent error envelope and never leaks stack traces.

### Technical analysis (1-week horizon)
- **Inputs:** about 3 years of daily OHLCV, adjusted for splits and dividends, and 60 days of 1-hour bars for session VWAP. Only completed candles count; today's live bar is excluded while the exchange is open, using exchange calendars for NYSE/NASDAQ and SGX.
- **Indicators (unit-tested against hand-computed fixtures):**
  - SMA and EMA (configurable periods; defaults 20/50 and 9/21)
  - RSI(14) with Wilder smoothing
  - MACD(12, 26, 9)
  - Bollinger Bands(20, 2)
  - ATR(14)
  - VWAP: session-reset on intraday bars; on the daily chart, anchored VWAP (default anchor is the start of the 1-week window, user-selectable)
- **Candlestick patterns:** doji, hammer, hanging man, inverted hammer, shooting star, bullish and bearish engulfing, bullish and bearish harami, piercing line, dark cloud cover, morning and evening star, three white soldiers, three black crows.
  - Each pattern has explicit geometric rules, for example engulfing requires O_t ≤ C_{t-1} and C_t ≥ O_{t-1}, with opposite candle colours.
  - Each pattern needs a minimum body size relative to ATR, so noise candles are not counted.
  - Trend context comes from the slope of SMA(10) and the close's position relative to it, computed only from bars **before** the pattern. Reversal patterns count only against the prevailing trend.
- **Per-stock reliability backtest:**
  - For every past occurrence, enter at the **next bar's open** (no look-ahead) and exit at the close 5 trading days later.
  - Report n, hit rate with a Wilson 95% confidence interval, and mean and median return.
  - Report **edge versus the base rate**, meaning the stock's unconditional 5-day up probability.
  - Patterns with n < 8 are marked "insufficient history".
- **Outlook:** a transparent weighted summary of the following, giving "Bullish lean", "Neutral" or "Bearish lean" with every contributing reason listed. It is labelled as an analytical signal, not advice.
  - patterns from the last 3 sessions, weighted by their measured edge
  - RSI regime
  - EMA 9/21 cross
  - price versus VWAP
  - MACD histogram slope
  - The expected 1-week range is ±ATR·√5.

### Macro analysis (2-year horizon)
1. **News ingestion:**
   - Backfill 24 monthly windows of Google News RSS (`"Company" after:… before:…`), throttled. Merge in results from the keyed providers.
   - A relevance filter keeps only stories whose headline or summary mentions the company name, an alias or the ticker.
   - After the backfill, ingestion is incremental.
2. **Sentiment:** FinBERT on the headline plus summary. Score = P(pos) − P(neg), in [−1, 1]. The model version is stored so articles can be re-scored later.
3. **Time alignment (critical for avoiding look-ahead):**
   - Convert `published_at` to the exchange's time zone (America/New_York or Asia/Singapore).
   - A story published after the close, or on a non-trading day, is mapped to the **next** trading session.
   - The daily sentiment index is the mean of the scores on that effective day, plus the article count. Days without news are excluded rather than treated as zero.
4. **Event study:**
   - Model the stock against its market: α and β come from OLS of the stock's returns on the benchmark's (SPY for US stocks; ^STI for SG, falling back to ES3.SI). The estimation window is trading days [−150, −20] before each event and must not overlap any event window.
   - Abnormal return AR = R − (α + βRₘ). Cumulative abnormal return (CAR) is computed over [0, 0], [0, +1] and [0, +5], plus a pre-event window [−5, −1] to catch anticipation or information leaking before the story.
   - News days less than 5 sessions apart are **clustered** into one event (with a sentiment weighted by article count), so overlapping windows don't inflate significance.
   - Statistics are shown both including and excluding events within ±1 day of earnings, so they are not confounded with earnings reactions.
5. **Statistics:**
   - Spearman ρ, with its p-value, between event sentiment and CAR[0, +1].
   - Average CAR by bucket: positive (> 0.3), neutral, negative (< −0.3). A Welch t-test compares positive with negative.
   - Any bucket with n < 10 shows "insufficient data", and the page notes that multiple comparisons were made.
6. **Output:**
   - A plain-English summary with **no bare "n" or "p"**. Example: "After positive news, the stock beat the market by +0.8% on average over the next 2 days. **Based on 34 news events.** **Likely a real effect:** if news had no influence, a gap this large would appear by chance only about 3 in 100 times."
     - The reliability label comes from the p-value: "Likely a real effect" (p < 0.05), "Weak evidence" (0.05–0.2), or "Could be chance" (≥ 0.2).
     - The exact figure is available only in an expandable "Details" row, labelled "p-value", with a ? tooltip explaining it.
     - The technical tab uses the same wording. For example: "Seen 12 times in the past 3 years; price was higher a week later 9 of 12 times (75%), versus 55% for a typical week."
   - A weekly sentiment timeline.
   - The 10 highest-impact events, with headlines and links.
   - The current regime: a z-score of the last 30 days' sentiment against the 2-year baseline.

### API (summary)
- `POST /auth/register|login|refresh|logout`, `GET /me`
- `GET|PUT|DELETE /watchlist[/{symbol}]`
- `GET /stocks/search?q=` (US exchanges and SGX only)
- `GET /stocks/{symbol}`: quote and profile
- `GET /stocks/{symbol}/chart?range=&interval=&indicators=`: bars, indicator series, and event markers for earnings, dividends, splits, patterns and high-impact news
- `GET /stocks/{symbol}/technical`
- `GET /stocks/{symbol}/macro`
- `GET /admin/providers`: quota and health status of the data providers
- `GET /admin/users`, `PATCH /admin/users/{id}` (enable, disable, role), `DELETE /admin/users/{id}`. Guards prevent deleting or demoting yourself or the last admin.

### Security
- Access JWT valid for 15 minutes; refresh tokens rotate and are revoked if reused.
- Tokens live in httpOnly, Secure, SameSite=Lax cookies, with a double-submit CSRF token.
- Login is rate-limited and accounts lock after repeated failures.
- Passwords must be at least 12 characters.
- CORS is restricted to an allow-list.
- The first admin is created only through the `python -m app.cli create-admin` command; registration can never grant admin.

## Frontend design
- **5 routes:** `/login`, `/register`, `/` (search plus watchlist), `/stock/:symbol`, `/admin` (admins only: a user management table plus the Data providers panel and quota alert banner, with no watchlist data).
- **Theme:** a custom MUI theme that is strictly monochrome (neutral greys, black and white). It follows the system light/dark preference by default, has a toggle in the top bar, and remembers the choice. Up and down prices use muted green and red **plus** ▲/▼ signs, so meaning never depends on colour alone. Spacing follows an 8pt grid, the type scale is restrained, and prices use tabular numerals.
- **Home page:** search with an autocomplete showing an exchange badge (US or SGX). The watchlist table shows symbol, last price, 1-week change, a sparkline and the outlook badge. There are empty, loading (skeleton) and error states.
- **Stock page:**
  - A header with the price, change and a ☆ watchlist toggle.
  - The chart: a lightweight-charts candlestick with a volume histogram. Event markers (E for earnings, D for dividends, S for splits, pattern glyphs, and dots for news impact) show details on hover.
  - Indicator toggle chips for VWAP, SMA, EMA, Bollinger, RSI and MACD. RSI and MACD get their own synced sub-panes.
  - A range selector (1W, 1M, 6M, 1Y, 2Y).
  - Below the chart, **Technical (1 week)** and **Macro (2 years)** tabs show only the essential numbers, with the details available on expand.
- **Jargon help:** a `<Term id="rsi">` component draws a ? icon with a tooltip (keyboard-focusable, tap-friendly) whose text comes from a single `glossary.ts`. It covers every indicator, pattern and stat (CAR, abnormal return, p-value, Wilson CI…).
- **UI iteration loop:**
  1. Run the app in the built-in browser pane and screenshot every page at 1440px and 375px, in light and dark mode.
  2. Critique the screenshots against a senior UI/UX checklist: hierarchy, spacing rhythm, alignment, WCAG AA contrast, focus rings, states, layout shift, density, chart legibility. Use an independent reviewer subagent plus any design skills that find-skills turns up.
  3. Fix the issues, and repeat until a full pass finds no remaining issues.
  4. Commit the final Playwright screenshots to the PR description.

## Quality loop (backend first, then frontend)
1. Tests: aim for at least 90% coverage on `domain/`. Hypothesis property tests check invariants such as RSI ∈ [0, 100], that no pattern uses future bars, and that the alignment never maps a story to an earlier session. Provider tests simulate 429s, 5xx errors, timeouts and malformed payloads. Integration tests cover auth flows and admin isolation.
2. Run **thermo-nuclear-code-quality-review** and **improve-codebase-architecture** as their instructions say, apply the findings, and re-run until they come back clean. Then run `/code-review` (high) and `/security-review`.
3. An independent subagent audits the analysis logic for look-ahead bias, survivorship issues, overlapping windows and statistical misuse. Iterate until it finds nothing.
4. Gates: ruff, mypy strict, ESLint and tsc must report zero errors, and CI must be green.

## GitHub and PRs (private repo `nichtg/StockEye`)
- `main`: one initial commit (README, .gitignore, .editorconfig, LICENSE placeholder). Everything else arrives through PRs.
- **PR 1** `feat/backend-foundation`: app skeleton, config, Mongo, auth, users, admin, watchlist, the resilience layer, backend CI, `docs/REPORT.md` and `docs/ARCHITECTURE.md`.
- **PR 2** `feat/backend-analysis` (stacked on PR 1): providers, ingestion jobs, FinBERT, the technical and macro engines, and the stocks API.
- **PR 3** `feat/frontend` (stacked on PR 2): the whole UI, frontend CI, Dockerfiles and compose, and screenshots in the description.
- Each PR description covers scope, design notes, test evidence and the merge order (1 → 2 → 3). Commits and PR bodies carry the requested attribution lines. Auto-merge stays off.

## Verification
- `uv run pytest` (unit, providers and integration against the local Mongo test database), plus `ruff` and `mypy`.
- `npm run lint && npm run typecheck && npm test && npm run build`; then Playwright end-to-end tests:
  - register, then log in
  - search for AAPL and D05.SI
  - open the chart, toggle indicators, hover a marker
  - add to the watchlist
  - toggle the theme
  - as admin: manage users and confirm no watchlist data is exposed
- A manual run in the browser pane for US (AAPL, MSFT) and SG (D05.SI, Z74.SI) stocks. Force failures by setting a bad provider key, blocking the network, or exhausting a quota, and confirm the stale/partial banners appear instead of errors. In the quota test, also confirm the 80% WARNING and limit ERROR log lines, and that the admin page shows the alert banner.
- Spot-check indicator values against Yahoo or TradingView for 2–3 symbols.
- CI green on all PRs.

## Limitations to note in the report
- yfinance and Google News RSS are unofficial and may change.
- Google News coverage of small-cap SG stocks is thin.
- FinBERT scores headlines only.
- The analytics are informational, not investment advice; a disclaimer appears in the UI footer.
- Docker images are checked in CI only, because Docker is not installed locally.

---

## Status (2026-10-03)

### Branches
Each branch is stacked on the one before it, and nothing is pushed yet except `main`.

| Branch | Contents | State |
|---|---|---|
| `main` | Initial scaffold | Pushed |
| `feat/backend-foundation` | Skeleton, auth, accounts, admin, watchlist, provider resilience | Passes CI-equivalent gates on its own (135 tests) |
| `feat/backend-analysis` | Providers, FinBERT, technical and macro engines, services and API, refactors, security hardening, docs, Docker | 726 tests. **Thermo-nuclear review: APPROVED (round 5).** |
| `feat/frontend` | The whole UI, frontend CI, nginx and Dockerfile, curated screenshots | 107 tests. **Frontend review round 2: NOT APPROVED**; all 4 Majors and 8 Minors since fixed and committed; round-3 re-review pending. |

### Review history
- **Analysis-logic audit (Opus):** 1 Critical, 9 Major and 12 Minor findings. All fixed, with regression tests.
- **Architecture (improve-codebase-architecture):** the user picked deepenings 1, 2 and 3, and all are implemented.
- **Backend thermo-nuclear review:** rounds 1–4 were not approved; round 5 was APPROVED.
- **Backend security review:** 0 Critical, 3 High, 4 Medium and 9 Low. All High and Medium fixed; the Lows were fixed or documented.
- **Frontend thermo-nuclear plus Web Interface Guidelines:**
  - Round 1: NOT APPROVED. Fixed in passes FA and FB.
  - Round 2: NOT APPROVED, with 4 small Majors. Fixed in commit 585f1f9.

### Remaining steps
1. **Frontend re-review round 3.** Check against `.handoff/sdd/frontend-fix-round-2.md`. If it isn't approved, fix and re-review.
2. **Re-shoot `frontend/screenshots/admin-desktop-light.png`.** It is stale. Create an admin via `uv run python -m app.cli create-admin`, with credentials only in shell env, then run `node scripts/screenshots.mjs` with `SE_ADMIN_EMAIL` and `SE_ADMIN_PASSWORD` set.
3. **Known non-blocking minors:**
   - The RSI "40.00" axis label sits close to the value badge.
   - The watchlist Undo toast is lost when navigating away (a toast host would belong in AppShell).
   - Two cache payload formats share one collection (backend).
   - A crash-only state where `last_bar_at` is set but no bars exist answers 404 for up to 15 minutes.
4. **Push and open PRs**, merged in order 1 → 2 → 3:
   - `git push -u origin feat/backend-foundation feat/backend-analysis feat/frontend`
   - PR 1: `feat/backend-foundation` → `main`
   - PR 2: `feat/backend-analysis` → `feat/backend-foundation`
   - PR 3: `feat/frontend` → `feat/backend-analysis`

   Each PR description covers scope, design notes, test evidence and the merge order, and ends with the 🤖 Claude Code attribution line. Commits use the `Co-Authored-By: Claude Opus 5.5` trailer.
5. **Watch CI on the PRs** and fix any failures. The workflows are `backend.yml` (with a mongo:8 service), `frontend.yml`, `docker.yml` and pip-audit/npm audit.
6. **Give the user the final report**, summarizing `docs/REPORT.md`, with the PR links.
