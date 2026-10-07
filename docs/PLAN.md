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

## Status (2026-10-04)

### Branches
Each branch is stacked on the one before it. All four are pushed, with PRs open (see "Remaining steps").

| Branch | Contents | State |
|---|---|---|
| `main` | Initial scaffold | Pushed |
| `feat/backend-foundation` | Skeleton, auth, accounts, admin, watchlist, provider resilience | 135 tests |
| `feat/backend-analysis` | Providers, FinBERT, technical and macro engines, services and API, refactors, security hardening, docs, Docker | 726 tests. **Thermo-nuclear review: APPROVED (round 5).** |
| `feat/frontend` | The whole UI, frontend CI, nginx and Dockerfile, curated screenshots in `docs/screenshots/` | 110 tests. **Frontend review: APPROVED (round 3).** |

### Review history
- **Analysis-logic audit (Opus):** 1 Critical, 9 Major and 12 Minor findings. All fixed, with regression tests.
- **Architecture (improve-codebase-architecture):** the user picked deepenings 1, 2 and 3, and all are implemented.
- **Backend thermo-nuclear review:** rounds 1–4 were not approved; round 5 was APPROVED.
- **Backend security review:** 0 Critical, 3 High, 4 Medium and 9 Low. All High and Medium fixed; the Lows were fixed or documented.
- **Frontend thermo-nuclear plus Web Interface Guidelines:**
  - Round 1: NOT APPROVED. Fixed in passes FA and FB.
  - Round 2: NOT APPROVED, with 4 Majors. Fixed in commit 585f1f9.
  - Round 3: APPROVED, with 8 Minors. They were fixed (an app-wide notice host, so toasts survive navigation), and the fix delta was re-reviewed until APPROVED.

### Known non-blocking minors
- The RSI "40.00" axis label sits close to the value badge.
- Two cache payload formats share one collection (backend).
- A crash-only state where `last_bar_at` is set but no bars exist answers 404 for up to 15 minutes.
- A sentiment `scoring_error` is cleared only on the next news ingestion, so after installing the model the banner lingers until the next refresh.

### Remaining steps
All done:
1. Frontend review round 3: APPROVED.
2. Screenshots re-shot, including `admin-desktop-light.png`.
3. PRs open, to be merged in order 1 → 2 → 3:
   - [#1](https://github.com/nichtg/StockEye/pull/1): `feat/backend-foundation` → `main`
   - [#2](https://github.com/nichtg/StockEye/pull/2): `feat/backend-analysis` → `feat/backend-foundation`
   - [#3](https://github.com/nichtg/StockEye/pull/3): `feat/frontend` → `feat/backend-analysis`
4. CI is green on all three PRs.
5. Final report delivered.

## Phase 2 (2026-10-04): news experience, event-study fix, account deletion

The user reviewed the merged app and chose, from a report of causes, flaws and options: 1B, 2B, 3A+3B, 4A, 5A+5B+5F and 6A.
5C was dropped because 5A already covers it, and 7 was dropped.

| Item | What changed |
|---|---|
| 4A (bug) | The event study masked every news event's window out of every estimation window, so on heavily covered stocks almost all events after the first months were discarded (16 of 87 evaluated in the regression fixture, 87 of 87 now). The market model now uses [t-250, t-20] and masks only earnings. AAPL: 45 events instead of about 10. |
| 5A / 5B / 5F | `GET /stocks/{symbol}/news` starts collection when a stock page opens (validated and admission-checked), backfills newest month first, and reports an honest status. |
| 1B | Preliminary chip while collecting; "News complete: 24 months, updated ..." line and a notice when done. |
| 2B | Biggest news days: Newest / Biggest move switch. |
| 3A / 3B | Every evaluated news event is a chart marker sized by its move, refreshed once the newest months arrive; marker chips show counts and explain when empty. |
| 6A | `DELETE /me` with password re-check, CSRF, per-IP and per-account limits, lockout, and a safe last-admin guard; a "Delete account" dialog in the account menu. |

Reviews:
- Opus methodology audit of 4A: APPROVED.
- Backend thermo-nuclear review: approved in round 2.
- Security review: 2 Medium and 3 Low, then 3 more Low on re-check; all fixed.
- Frontend review: approved in round 3.

Tests: backend 767, frontend 134.

## Phase 3 (approved 2026-10-04): clearer news wording, recap-headline filter, latest-pattern hint, toast notice

The user reviewed the merged phase-2 app and chose 1A, 2A+2B, 4A, 6A+6B+6C and 7A. 2C, 6D, 4B, 4C and pattern time-weighting were declined.

Branches (stacked, each with its own PR):
- `feat/backend-news-clarity`, from `main`
- `feat/frontend-news-clarity`, from the backend branch

### Backend
Two Sonnet tasks run in parallel, each owning its own files.
- **C1: price-recap headline filter (6C).**
  - A pure rule-based `is_price_recap(title)` in `domain/macro/` flags headlines that only report a move ("shares up 34%", "stock falls", "trading higher", "why X stock is soaring today", "X moved down 4.79% on Jun 25").
  - Flagged articles are excluded when macro inputs are read, not at storage, so stored news is cleaned at once. Bump the macro cache version.
  - Tests: a labelled headline list (precision and recall) and a check that event headline lists contain no recaps.
  - Report before/after counts and statistics on live AAPL and RKLB.
  - Opus methodology audit (false positives, no bias introduced).
- **C2: wording and data (2A, 2B, 4A).**
  - 2A: reliability labels become "Clear news effect", "Possible news effect" and "No clear news effect", with one source of wording.
  - 2B: when the all-days scope is clear (p < 0.05) but the primary ex-earnings scope isn't, add the note "This effect comes mostly from news around earnings releases."
  - 4A: the technical report adds `latest_pattern {date, label, sessions_ago}`.
  - Tests for each.
- **Then:** run the gates, regenerate `openapi.json` and the frontend types, run the Opus thermo-nuclear review, and fix until approved. No security review is needed: there are no new endpoints or auth changes.

### Frontend
One Sonnet task, after the types are regenerated.
- **1A:** `<Term>` text sits on the line's baseline, and only the `?` icon is centred (`components/Term.tsx` currently uses `alignItems: center`, which lifts small text). Check every text size.
- **2A:** new labels with a neutral badge style.
- **2B:** show the earnings note.
- **4A:** "No patterns in the last 3 trading days. The most recent was a <label> on <date> (<n> trading days ago), too old to count in this week's outlook."
- **6A:** rows read "41.4% above its usual market-linked move", and the `?` tooltip explains the calculation: the abnormal return on the news day and the next day, against alpha + beta x market, fitted over [t-250, t-20].
- **6B:** an "Earnings" tag on rows with `near_earnings`.
- **7A:** move `NoticeProvider` to the app root, so public routes get toasts that auto-hide after 6 s and can be dismissed. The login page shows "Your account was deleted." as a toast. Delete the `signedOutNoticeKey` hand-off and the login Alert.
- **Then:** Opus review, and fix until approved.

### Verification
- Live run: the RKLB and AAPL macro tabs, the RKLB Technical tab, a deleted account's toast disappearing, and the term alignment.
- Re-shoot the screenshots.
- Push, open two PRs (backend → main, frontend → backend branch), get CI green, and merge only when the user asks.

### Phase 3 status
- [x] C1 recap filter, plus the Opus audit (approved; AAPL 53/1991, RKLB 112/686, SNDK 247/792 flagged)
- [x] C2 wording and data
- [x] Backend thermo review approved (889 tests)
- [x] F1 frontend, plus the Opus review approved
- [x] Live verification and screenshots
- [x] PRs open and CI green; merged (#6, #7)

## Phase 4 (approved 2026-10-04): "?" icon alignment and dated, averaged macro findings

The user reviewed the merged phase-3 app and chose, from `.handoff/sdd/report-P4.md`, 1A and 3A+3B+3C. 1B and 3D were declined.

Branches (stacked, each with its own PR):
- `feat/backend-macro-clarity`, from `main`
- `feat/frontend-macro-clarity`, from the backend branch

### Backend
One Sonnet task (B1).
- **3A data:** each scope's statistics (`MacroStats` / `MacroStatsOut`) gain `first_event` and `last_event`, the dates of the
  earliest and latest events that scope used (None when it used none). The UI never re-derives which events a scope used.
- **3B wording:** findings in `domain/macro/summary.py` say they are averages and name the count, e.g. "On average, on the
  17 days with positive news, the stock did 0.1% better than its usual relationship with the market would predict (that
  day and the next)." The gap sentence likewise says "On average". Still no bare statistical letters.
- Bump `MACRO_CACHE_SCHEMA`; regenerate `openapi.json` and the frontend types.
- Tests for both; then an Opus methodology audit (the wording must match what is computed: the mean CAR[0,+1] per bucket)
  and the Opus thermo-nuclear review, fixing until approved. No security review: no new endpoints or auth changes.

### Frontend
One Sonnet task (F1), after the types are regenerated.
- **1A:** `<Term>`'s visible "?" is sized from its text (about 1.1em) and centred on the text's middle, so it lines up at
  every typography size; an invisible hit area of at least 24 px keeps it tappable without changing line height.
- **3A:** under "What the news has done to the price": "Based on news from <first month> to <last month>. Each result
  compares the stock's move on a news day and the next trading day with what the market predicted." Taken from the
  primary scope's stats; the secondary scope in Details gets its own period line.
- **3C:** a breakdown line that reconciles the counts: "29 news events: 17 positive, 7 neutral, 5 negative", each count
  with a "?" defining it (positive above +0.3 sentiment, negative below -0.3, neutral in between).
- Opus review, fixing until approved.

### Verification
- Live run on `stockeye_shots`: D05.SI, AAPL and RKLB macro tabs; the "?" beside caption, body2, body1, subtitle and chip
  text, at 1440 and 375 px in light and dark.
- Re-shoot the curated screenshots into `docs/screenshots`.
- Push, open two PRs (backend → main, frontend → backend branch), get CI green, and merge only when the user asks.

### Phase 4 status
- [x] B1 period dates and averaged wording (counts say "news days studied"; sign-aware pre-move caveat)
- [x] Backend methodology audit and thermo review approved (896 tests)
- [x] F1 icon alignment, period line and breakdown line (plus one "news days" noun, reconciled Details counts)
- [x] Frontend Opus review approved (round 3; 155 tests)
- [x] Live verification and screenshots (admin shot unchanged: admin page untouched)
- [x] PRs open and CI green; merged (#8, #9)

## Phase 5 (approved 2026-10-04): $0 deployment, frontend on GitHub Pages, backend on an Oracle free VM

The user asked to deploy with the frontend on GitHub Pages, keeping every secret safe, and approved a $0 plan.
A senior-pentester review (Opus, 3 rounds) signed it off with changes, which are folded in below.
The custom domain, Fly.io and is-a.dev were considered and declined.

### Architecture
- Frontend: GitHub Pages at `https://nichtg.github.io/StockEye/` (user's choice, 2026-10-05, over a dedicated org).
  Binding rule: no other repo of `nichtg` may enable Pages, since every such site would share this origin's
  localStorage and the API's CORS trust. The repo is public after a full-history gitleaks scan.
- Backend: an Oracle Cloud Always Free Arm VM on a reserved public IP. Docker compose runs Caddy (the only published
  ports, 80/443), the API and MongoDB (internal network only, auth on). HTTPS is a Let's Encrypt IP-address certificate
  (`shortlived` profile, auto-renewed by Caddy) plus HSTS. If a reserved IP isn't free, the fallback is an is-a.dev
  hostname.
- Cross-site (github.io is on the Public Suffix List), so auth moves from cookies to bearer tokens.

### Branches (stacked, each with its own PR)
- `feat/token-auth`, from `main`: backend and frontend auth migration, which must land together.
- `feat/deploy`, from `feat/token-auth`: images, VM setup, Caddy, workflows and runbook.

### Token auth (feat/token-auth)
- **Backend (Sonnet):**
  - The principal comes only from `Authorization: Bearer` (15-minute access JWT).
  - Login, register and refresh return `{access_token, refresh_token, ...}` in the body; refresh and logout take the
    refresh token in the JSON body.
  - Delete every cookie set and read, the CSRF middleware and `/auth/csrf`.
  - CORS: exact origins, `allow_credentials=False`, allowing `Authorization` and `Content-Type`.
  - Absolute session cap: `family_started_at`, and rotation is refused after 30 days.
  - Password change, admin disable and account deletion revoke all families; logout revokes the family.
  - `mongodb_uri` becomes `SecretStr`.
  - Tests: a cookie-only request gets 401, the cap, reuse detection, and revocation.
- **Frontend (Sonnet), after the types are regenerated:**
  - Access token in memory; refresh token in localStorage.
  - Refresh runs under a cross-tab Web Locks lock and re-reads the stored token inside it.
  - On a 401: refresh once, then retry. Logout clears storage.
  - `VITE_API_BASE_URL` and the Pages base path come from build env; `404.html` is a copy of `index.html`; no
    source maps.
  - A meta CSP whose `connect-src` is the API origin, plus a hide-until-verified frame-buster.
  - Local docker compose keeps working same-origin.
- Reviews: an Opus security review of the auth migration and an Opus thermo review; fix until approved.

### Deploy (feat/deploy, Sonnet)
- **Arm64 image:**
  - Built on GitHub's free `ubuntu-24.04-arm` runner and pushed to GHCR.
  - The deploy is by **digest**, over SSH.
  - The SSH key in the GitHub `production` environment is restricted by an authorized_keys forced command, with
    no-pty and no forwarding.
  - The deploy script accepts only `sha256:[0-9a-f]{64}`, and the host key is pinned in the workflow.
- **VM setup script:**
  - Unattended upgrades with automatic reboot; SSH key-only with no root login; Oracle iptables plus security list
    open on 22/80/443 only.
  - Docker; a root-only 0600 env file for secrets.
  - Nightly mongodump to private OCI Object Storage via instance principal, with retention.
- **Caddy:**
  - IP certificate and HSTS.
  - It overwrites X-Forwarded-For; uvicorn trusts only Caddy's address.
- **Workflows:**
  - Every workflow starts with `permissions: {}`, and jobs are split (build/test, image push, deploy).
  - Actions are pinned to SHAs.
  - A Pages deploy via OIDC.
  - A gitleaks workflow, plus a dist secret-pattern grep.
  - Dependabot.
  - A daily health and certificate-expiry check that fails loudly.
- **Runbook (`docs/DEPLOY.md`):**
  - The user's one-time steps (Oracle account; Pay-As-You-Go optional, 1 OCPU / 6 GB so memory stays above the idle threshold; a reserved
    IP, the admin over getpass).
  - Rotation of each secret.
  - Teardown order: delete DNS records and config before releasing the IP or deleting the site.
- **Reviews:** an Opus security review of all deployment code; fix until approved.

### Go-live probes
- A cookie-only request returns 401.
- Two tabs refresh without logging out.
- Spoofed X-Forwarded-For is ignored.
- Mongo is unreachable from outside, and a port scan shows only 22/80/443.
- CORS from a foreign origin and from the `null` origin is refused.
- Framing is hidden.
- TLS and header scan; gitleaks clean; no key patterns in dist.

### Accepted residual risks
- XSS could ride a session (mitigated by strict CSP, rotation and reuse detection).
- Register enumeration (rate-limited) and the 15-minute lockout.
- Single VM, no WAF.
- Oracle capacity and reclaim risk.

### Phase 5 status
- [x] Backend token auth (refresh families, 30-day cap, refresh rate limit, validated CORS; 935 tests)
- [x] Frontend token client (Web Locks, compare-and-set, timeouts, frame gate; 207 tests)
- [x] Auth security reviews approved (backend 2 rounds, frontend 3 rounds); live two-tab test OK
- [x] Deploy infrastructure (deploy/, workflows, docs/DEPLOY.md runbook)
- [x] Deploy security review approved (3 rounds; pins and image digests verified over the network)
- [x] PRs open and CI green; merged (#10, #11)
- [x] User one-time setup; live since 2026-10-07 (API https://168.107.88.248, site https://nichtg.github.io/StockEye/)
  - Fixes found on the real VM: Ubuntu's `admin` group (#20), MongoDB 8 vs the 7.0 kernel, so MongoDB 7.0 (#21, #23),
    Caddy's fixed IP taken by the API (#22, plus a flaky race test), Pages tests getting the base path (#24).
  - External probes passed: valid IP certificate, HTTP to HTTPS, 404 outside /api, docs hidden, CORS exact
    (foreign and null origins refused), only 22/80/443 open, a spoofed X-Forwarded-For can't dodge the login limit
    (429 after 10), backup upload via instance principal, container DNS.
- [ ] Admin account created; a day later the memory check (DEPLOY.md step 3.6); lifecycle rule confirmed
