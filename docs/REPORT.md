# StockEye: technology report

This report covers what StockEye is built with, what each piece is for, how the analysis works, how the system fails gracefully, and the known limitations. Module-level structure is in [ARCHITECTURE.md](ARCHITECTURE.md).

## 1. Technology choices

### Backend (`backend/`)
| Concern | Choice | Why / what it does |
|---|---|---|
| Language | **Python 3.13** (pinned with **uv**) | Best ecosystem for numeric and NLP work. Pinned to 3.13 because onnxruntime and scipy ship stable wheels for it. |
| Web framework | **FastAPI** + **Pydantic v2** + **pydantic-settings** | Typed request/response models, automatic OpenAPI (the frontend generates its TypeScript types from it), and environment-based configuration (`STOCKEYE_*`). |
| ASGI server | **uvicorn** | Runs the app (`uvicorn app.main:create_app --factory`). |
| Database | **MongoDB** (non-relational), via PyMongo's native **async** client | Document store for users, watchlists, price bars (a **time-series collection**), corporate events, news articles, an analysis cache (TTL), and provider quota and health state. Runs locally in development (MongoDB Community 9.0 as a Windows service) and on **MongoDB Atlas** in production (set `STOCKEYE_MONGODB_URI=mongodb+srv://…`). |
| Numerics | **pandas**, **numpy**, **scipy.stats** | Indicators, candlestick detection, the event study, and statistical tests (Spearman, Welch's t, one-sample t, Wilson intervals). |
| Trading calendars | **exchange-calendars** | Real NYSE and SGX sessions, holidays and early closes, used to map news timestamps to trading sessions and to exclude in-progress bars. |
| Sentiment | **FinBERT** (ProsusAI/finbert, ONNX export from `Xenova/finbert`, int8-quantized) run through **onnxruntime** + **tokenizers** | Local, free, deterministic scoring of financial headlines. Score = P(positive) − P(negative). |
| HTTP client | **httpx** (async) | All vendor API calls, with explicit timeouts. |
| Market data | **yfinance** | Prices (split- and dividend-adjusted), quotes, search, earnings dates, dividends and splits for US and `.SI` (SGX) tickers. |
| News | **Google News RSS** (keyless, date-windowed, SG and US editions) plus optional **Finnhub**, **Marketaux** and **Alpha Vantage** (enabled automatically when their free API keys are set) | Two years of news history. Keyed providers add depth for recent US news. |
| RSS parsing | **feedparser** | Parses Google News RSS. |
| Scheduling | **APScheduler** | Post-close refresh of watchlisted US (21:30 UTC) and SGX (09:30 UTC) symbols. |
| Auth | **argon2-cffi** (argon2id), **PyJWT**, **limits** | Password hashing, short-lived access tokens, and fixed-window rate limits (per IP on the auth routes, per user on the data routes). |
| Logging | **structlog** (JSON) | Structured logs with a request id on every line, and loud quota warnings. |
| Quality tooling | **ruff**, **mypy --strict**, **import-linter**, **pytest** (+ pytest-asyncio, respx, hypothesis, time-machine) | Lint and format, strict typing, enforced layering rules, and over 700 tests including property-based tests. |

### Frontend (`frontend/`)
| Concern | Choice | Why / what it does |
|---|---|---|
| Framework | **React 19** + **TypeScript** (strict) + **Vite** | A fast SPA build with type safety. |
| UI kit | **MUI v7**, with a custom monochrome theme | Material components restyled to the black/white design system, with light and dark modes (system default, toggle persisted). |
| Data fetching | **TanStack Query v5** | Caching, retries, polling (for macro ingestion progress) and optimistic watchlist updates. |
| Routing | **React Router v7** | Five routes: `/login`, `/register`, `/`, `/stock/:symbol`, `/admin`. |
| Charts | **TradingView lightweight-charts v5** | Candlesticks, volume, indicator overlays, RSI and MACD sub-panes, and event markers (earnings, dividends, splits, patterns, high-impact news). |
| API types | **openapi-typescript** | Types generated from the backend's OpenAPI, so the frontend and backend contracts cannot drift silently. |
| Font | **IBM Plex Sans** (self-hosted via @fontsource) | Tabular numerals for prices; no third-party font CDN. |
| Testing | **Vitest** + **Testing Library**, **Playwright** | Unit and component tests, plus scripted screenshot walkthroughs. |

### Delivery
- **GitHub Actions**:
  - `backend.yml`: ruff, mypy, import-linter and pytest against a MongoDB 8 service container.
  - `frontend.yml`: lint, typecheck, tests and build.

## 2. How the analysis works

### Technical (1-week horizon)
1. **Indicators** follow TradingView conventions: SMA, EMA (SMA-seeded), Wilder RSI(14), MACD(12, 26, 9), Bollinger Bands(20, 2σ, population), Wilder ATR(14), session VWAP (intraday) and anchored VWAP (daily).
2. **Candlestick patterns.** There are 15: doji, hammer, hanging man, inverted hammer, shooting star, bullish and bearish engulfing, bullish and bearish harami, piercing line, dark cloud cover, morning and evening star, three white soldiers, and three black crows.
   - Each has explicit geometric rules and a minimum size relative to ATR.
   - Reversal patterns count only against the prevailing trend.
   - The trend is measured **only from bars before the pattern**.
3. **Per-stock reliability.**
   - For every past occurrence of a pattern on *this* stock, we buy at the **next bar's open** and sell at the close 5 sessions later. This avoids look-ahead.
   - Occurrences whose holding periods would overlap are skipped.
   - The hit rate is compared against a **base rate measured in the same trend context**, with a Wilson 95% interval.
4. **Outlook.** A transparent weighted summary:
   - patterns that have *credibly* beaten the base rate (Wilson lower bound above it, at least 15 occurrences)
   - RSI regime
   - EMA 9/21 cross
   - price versus weekly VWAP
   - MACD momentum

   The result is "Bullish lean", "Neutral" or "Bearish lean", with every reason listed, plus a typical 1-week range (close ± ATR·√5, which contains about 9 in 10 weeks).

### Macro (2-year horizon)
1. **News collection.**
   - 24 monthly Google News windows are backfilled, then refreshed incrementally. Keyed providers are added when configured.
   - Articles are de-duplicated and filtered for relevance (the company's core name or ticker must appear).
   - Each article is scored with FinBERT.
2. **Timing without look-ahead.**
   - Each article maps to the **first trading session whose close is after publication**, using the real exchange calendar (America/New_York or Asia/Singapore).
   - After-hours and weekend news therefore counts toward the next session.
3. **Event selection.**
   - News days are turned into non-overlapping events using causal, bounded windows. Future news cannot change which past events were selected.
   - This prevents overlapping windows from inflating significance on heavily covered stocks.
4. **Event study.**
   - A market model (α, β from OLS against SPY for US stocks or the STI for SGX stocks, estimated on the 231 sessions from −250 to −20 before the event, excluding only earnings days; other news days stay in, because heavily covered stocks have news almost daily and masking them all would leave no clean days, while their effect on a 231-day fit is small) gives the **abnormal return**: how much better or worse the stock did than its usual relationship with the market would predict.
   - We measure that over the news day and the next day, and over 5 days.
   - The pre-event drift (−5 to −1) is reported as a caveat.
5. **Statistics.**
   - Spearman correlation between sentiment and abnormal return.
   - Per-bucket one-sample t-tests for positive and negative news.
   - A Welch t-test between positive and negative news.
   - Any statistic with fewer than 10 events is withheld.
   - Results are shown with and without days near earnings releases.
6. **Plain language.**
   - The UI never shows a bare "n" or "p". Findings read like "Based on 34 news events. Likely a real effect: if news had no influence, a gap this large would appear by chance only about 3 in 100 times."
   - Exact p-values live under "Details".
7. **Sentiment regime.** The last 30 days are compared with the distribution of earlier 30-day blocks, as a z-score.

An independent audit (by a separate reviewer model) checked all of the above for look-ahead, off-by-one errors, statistical misuse and misleading wording. It found 1 critical issue (the bearish base rate counted zero-return days), 9 major issues and 12 minor ones. Each finding was fixed with a regression test that fails on the old code.

## 3. Graceful failure
- **Every vendor call** goes through a guarded adapter, which provides:
  - explicit timeouts
  - retries with exponential backoff and jitter (honouring `Retry-After` on 429s)
  - a circuit breaker per provider
  - a MongoDB quota ledger that blocks calls *before* a free-tier limit is hit
- **Quota visibility:**
  - A `provider_quota_warning` WARNING is logged once per day at 80% of a provider's limit.
  - A `provider_quota_exhausted` ERROR is logged once when calls start being blocked.
  - A `provider_quota_reset` INFO is logged when the window rolls over.
  - Vendor 429s are logged as ERROR.
  - The **admin page** has a Data providers panel (usage versus limit, reset time, breaker state, last error) and shows a banner whenever any provider is near or at its limit.
- **Cache-first reads.** When a refresh fails, the last saved data is served, flagged `stale`, with a plain-English reason ("Price data is 3 hours old: Yahoo Finance hit its rate limit. Showing the last saved prices."). Partial news collection shows progress instead of failing.
- **Failures don't cascade.** One failing symbol never breaks the watchlist, and the backfill pauses on per-minute limits and stops cleanly on daily ones.
- **Errors.** A single error envelope is used everywhere, with a request id. Stack traces are never returned to clients.

## 4. Security
- Passwords are hashed with argon2id, with a 12-character minimum.
- Logins are rate-limited per IP, and accounts lock after repeated failures. Unknown-email and wrong-password logins take equal time.
- Sessions use httpOnly cookies: a 15-minute access JWT plus a rotating refresh token with **reuse detection**, where a replayed token revokes the whole session family.
- Every state-changing request needs a double-submit **CSRF** token.
- The **admin cannot see watchlists.**
  - The admin API exposes no watchlist data.
  - An import-linter contract forbids the admin module from importing the watchlist modules.
  - Integration tests assert both.
- Admins cannot demote, disable or delete themselves or the last admin. The first admin is created only through the CLI (`uv run python -m app.cli create-admin`).
- **Accepted trade-off: 15-minute access tokens.** A stolen access JWT cannot be revoked by itself and works until it expires, at most 15 minutes. The API re-reads the user on every request, so disabling a user or changing a role still applies immediately, and a lockout deliberately does not end sessions. A shorter TTL would only add refresh traffic, so it stays at 15 minutes.
- Passwords from the 10,000 most common list (SecLists, MIT) are rejected. Hashing and verifying run off the event loop, and failed-login attempts are reserved atomically, so concurrent guessing cannot exceed the cap.
- Secrets never reach logs: `httpx`/`httpcore` are quiet, every log line is scrubbed of `token=`/`apikey=` values, and Finnhub's key travels in a header. The JWT secret has no default and must be strong outside tests.
- The API trusts `X-Forwarded-For` only from the compose subnet, nginx overwrites it with the real peer address and rate-limits `/api/auth/`, and the SPA is served with a Content-Security-Policy. MongoDB requires a login in compose, the FinBERT download is pinned to a commit and checksummed, and CI audits Python and npm dependencies.

## 5. Code-quality process
- **Implementation.** Each clearly scoped module was built by a focused implementer agent (Sonnet 5.5) from a written brief, then reviewed.
- **Skills applied:**
  - `thermo-nuclear-code-quality-review`. The first verdict was not approved, with 15 findings; all were addressed.
  - `improve-codebase-architecture` (with `codebase-design`). You chose deepenings 1–3, all of which were implemented: guarded adapters, a single quota-ledger interface, and a deeper account module.
  - Testing: `python-testing-patterns`.
  - Execution: `subagent-driven-development`.
  - Frontend: `frontend-design`, `web-design-guidelines`, `vercel-react-best-practices`, `webapp-testing`.
  - Charts: `dataviz`.
  - Skill discovery: `find-skills`.
- **Gates on every change:** ruff, mypy --strict, import-linter (domain purity, layering, admin/watchlist isolation) and the full test suite.

## 6. Known limitations
- yfinance and Google News RSS are unofficial interfaces and may change. The provider adapters isolate that risk.
- Google News coverage of small-cap SGX stocks is thin, so macro findings for those stocks often show "not enough news events yet".
- FinBERT scores headlines and summaries, not full articles.
- An SGX announcements feed was deliberately not integrated, because it has no documented public API.
- The analytics are informational, **not investment advice**. A disclaimer is shown in the UI footer.
- Docker images are verified in CI only, because Docker is not installed on the development machine.
