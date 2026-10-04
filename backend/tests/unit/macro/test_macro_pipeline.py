"""Whole-pipeline checks: alignment -> event study -> statistics, without look-ahead."""

from datetime import date, datetime, time

import numpy as np
import pandas as pd
from macro_helpers import NY, build_market, make_calendar

from app.domain.macro import (
    ScoredArticle,
    compute_stats,
    daily_sentiment,
    run_event_study,
    sentiment_regime,
    weekly_timeline,
)

N = 500
AS_OF_POS = 400
CAL = make_calendar(date(2023, 1, 2), N)
NEWS_POSITIONS = [*range(60, 391, 14), 405, 420, 450, 480]  # last four lie after as_of


def _articles(positions: list[int]) -> list[ScoredArticle]:
    rng = np.random.default_rng(3)
    out = []
    for pos in positions:
        session = CAL.sessions[pos]
        ts = datetime.combine(session, time(11, 0), tzinfo=NY)  # intraday -> same session
        out.append(
            ScoredArticle(ts, float(rng.uniform(-1, 1)), f"headline {pos}", f"https://x/{pos}", "s")
        )
    return out


def _run(n_days: int, articles: list[ScoredArticle]):
    # Future jumps differ between the two runs only through the extra rows.
    jumps = {pos + 1: 0.01 * ((pos % 3) - 1) for pos in NEWS_POSITIONS}
    stock, bench, _ = build_market(n=N, jumps=jumps)
    stock, bench = stock.iloc[:n_days], bench.iloc[:n_days]
    frame, _ = daily_sentiment(articles, CAL)
    events = run_event_study(stock, bench, frame, [])
    return frame, events


def test_pipeline_results_up_to_as_of_are_unchanged_by_future_prices_and_news():
    as_of = CAL.sessions[AS_OF_POS]
    all_articles = _articles(NEWS_POSITIONS)
    known = [a for a in all_articles if a.published_at.date() <= as_of]

    frame_cut, events_cut = _run(AS_OF_POS + 1, known)
    frame_full, events_full = _run(N, all_articles)

    # Only events whose whole [-5, +5] window ended before as_of are comparable.
    def settled(events):
        return [e for e in events if CAL.sessions.index(e.date) + 5 < AS_OF_POS]

    assert len(settled(events_cut)) >= 15  # guards against a vacuous comparison
    assert settled(events_cut) == settled(events_full)
    assert any(e.status == "ok" for e in settled(events_cut))
    assert compute_stats(settled(events_cut), exclude_near_earnings=False) == compute_stats(
        settled(events_full), exclude_near_earnings=False
    )
    assert sentiment_regime(frame_cut, as_of) == sentiment_regime(frame_full, as_of)
    cut_timeline = weekly_timeline(frame_cut)
    full_timeline = weekly_timeline(frame_full)
    assert full_timeline[: len(cut_timeline) - 1] == cut_timeline[:-1]


def test_pipeline_future_price_shock_does_not_change_earlier_event():
    stock, bench, index = build_market(n=N, jumps={150: 0.02})
    frame, _ = daily_sentiment(_articles([149]), CAL)
    base = run_event_study(stock, bench, frame, [])

    shocked = stock.copy()
    shocked.iloc[AS_OF_POS:] *= 3.0  # a crash/spike long after the event
    after = run_event_study(shocked, bench, frame, [])

    assert base == after
    assert isinstance(index, pd.DatetimeIndex)


def _scored(positions: list[int], scores: list[float]) -> list[ScoredArticle]:
    return [
        ScoredArticle(
            datetime.combine(CAL.sessions[pos], time(11, 0), tzinfo=NY),
            score,
            f"headline {pos}",
            f"https://x/{pos}",
            "s",
        )
        for pos, score in zip(positions, scores, strict=True)
    ]


def test_pipeline_clustered_news_closed_windows_are_unchanged_by_appended_news():
    # A 20-day chain (spacing <= 5) with rising salience, then another chain just before as_of.
    chain = [100, 104, 108, 112, 116, 120, 200, 203, 207, 211, 215, 380, 384, 388, 392, 396]
    scores = [0.2 + 0.03 * (i % 6) for i in range(len(chain))]
    future = [402, 405, 409, 412]
    future_scores = [0.95, 0.99, 0.97, 0.9]
    jumps = {pos + 1: 0.01 * ((pos % 3) - 1) for pos in chain + future}
    stock, bench, _ = build_market(n=N, jumps=jumps)

    def run(n_days: int, articles: list[ScoredArticle]):
        frame, _ = daily_sentiment(articles, CAL)
        return run_event_study(stock.iloc[:n_days], bench.iloc[:n_days], frame, [])

    cut = run(AS_OF_POS + 1, _scored(chain, scores))
    full = run(N, _scored(chain + future, scores + future_scores))

    def settled(events):
        return [e for e in events if CAL.sessions.index(e.date) + 5 < AS_OF_POS]

    assert len(settled(cut)) >= 5  # guards against a vacuous comparison
    assert settled(cut) == settled(full)
