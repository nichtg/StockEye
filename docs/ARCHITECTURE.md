# StockEye architecture

## Request flow
```
Browser (React SPA) ──/api──▶ FastAPI routers (app/api)
                                   │  deps: current user, CSRF middleware, error envelope
                                   ▼
                            Services (app/services)
          ┌────────────────────────┼─────────────────────────────┐
   MarketDataService         NewsService                  AnalysisService
   cache-first bars,         backfill + incremental,      technical / macro / chart,
   quotes, events            relevance, FinBERT scoring   pure compute off the event loop
          │                        │                             │
   guarded adapters ◀── ProviderGuard (retry, breaker, quota)    │
   (app/providers)                                              ▼
          │                                              Domain (app/domain): pure
   Yahoo / Google News / Finnhub / Marketaux / AV        technical/  macro/
          │
   Repositories (app/repositories) ──▶ MongoDB
```

## Layers (enforced by import-linter, see `backend/pyproject.toml`)
1. `app.main`: the app factory, lifespan and wiring.
2. `app.api`, `app.jobs`, `app.cli`: entry points. They stay thin and only translate HTTP, cron or CLI input into service calls.
3. `app.services`, `app.auth`: use cases and orchestration.
4. `app.repositories`, `app.providers`, `app.sentiment`: I/O adapters (MongoDB, vendors, the ONNX model).
5. `app.domain`: pure analysis. No I/O, no clock, and no pymongo, httpx or yfinance imports.

There are two more contracts:
- `app.domain` must stay pure.
- `app.api.admin` must never import the watchlist modules.

## Key modules and their interfaces
| Module | Interface | Hides |
|---|---|---|
| `providers.resilience.ProviderGuard` | `wrap_market(adapter)`, `wrap_news(adapter, wait_minute_quota=…)`, `statuses()` | Retries, backoff, the circuit breaker, the quota ledger, and quota-wait policy. Services never see any of it. |
| `services.market_data.MarketDataService` | `quote`, `search`, `daily_history`, `hourly_history`, `standard_events`, `company_name` | Cache freshness rules, stale fallback, dropping in-progress bars, and atomic bar replacement. |
| `services.news.NewsService` | `ensure_ingested`, `scored_articles` | 24-month backfill, the incremental pass, relevance filtering, dedupe, and scoring. |
| `services.analysis.AnalysisService` | `technical`, `macro`, `chart` | Assembling the domain pipelines, caching, and data-status reasons. |
| `services.accounts.AccountService` | `register`, `authenticate`, `start_session`, `rotate`, `end_session`, admin operations, `create_or_promote_admin` | Password policy, argon2, lockout, refresh rotation and reuse detection, and the last-admin guards. |
| `domain.technical` | indicators, `detect_patterns`, `pattern_reliability`, `build_outlook` | Pattern geometry, trend context, and backtest statistics. |
| `domain.macro` | `effective_session`, `daily_sentiment`, `run_event_study`, `compute_stats`, `build_macro_report` | Session alignment, event selection, the market model, statistical tests, and plain-language findings. |

## Data (MongoDB collections)
| Collection | Contents |
|---|---|
| `users` | Accounts |
| `refresh_tokens` | Session tokens, with TTL |
| `watchlists` | One document per owner |
| `price_bars` | Time-series collection |
| `price_fetch_state` | When each symbol's bars were last fetched |
| `corporate_events` | Earnings, dividends and splits |
| `news_articles` | Articles with their sentiment scores |
| `news_ingest_state` | News backfill and refresh progress |
| `analysis_cache` | Cached analysis results; stale copies are kept for 7 days, then removed by TTL |
| `provider_quota` | Quota usage per provider and window |
| `provider_health` | Last error per provider |

## Frontend
- `src/api`: a typed client generated from OpenAPI. It handles CSRF and a single shared refresh on 401.
- `src/theme`: tokens and the light/dark modes.
- `src/components/Term`: the glossary "?" tooltips.
- `src/features/{auth,admin,search,watchlist,stock,chart}`: one folder per feature.
- `src/pages`: five routes.
