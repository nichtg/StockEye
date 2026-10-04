import itertools
from datetime import date

import pandas as pd
import pytest
from macro_helpers import build_market, sent_frame

from app.domain.macro import run_event_study, select_events

TOL = 1e-9


def test_run_event_study_recovers_beta_and_known_abnormal_returns():
    # Jumps: +3% on day 200, -1% on day 201, -2% on day 300 (noise-free market model).
    stock, bench, index = build_market(jumps={200: 0.03, 201: -0.01, 300: -0.02})
    sent = sent_frame(index, {200: (0.8, 3), 300: (-0.7, 2)})

    res = run_event_study(stock, bench, sent, [])

    assert [r.date for r in res] == [index[200].date(), index[300].date()]
    first, second = res
    assert first.status == second.status == "ok"
    assert first.beta == pytest.approx(1.5, abs=TOL)
    assert first.alpha == pytest.approx(0.0002, abs=TOL)
    # The second event's window still contains the first event's jumps (not masked): the fit
    # is slightly biased but close.
    assert second.beta == pytest.approx(1.5, abs=0.1)
    assert first.car_0_0 == pytest.approx(0.03, abs=TOL)
    assert first.car_0_1 == pytest.approx(0.02, abs=TOL)  # 0.03 - 0.01
    assert first.car_0_5 == pytest.approx(0.02, abs=TOL)
    assert first.car_pre_5 == pytest.approx(0.0, abs=TOL)
    assert second.car_0_0 == pytest.approx(-0.02, abs=0.01)
    assert second.car_0_5 == pytest.approx(-0.02, abs=0.01)
    assert first.sentiment == 0.8
    assert first.article_count == 3


def test_run_event_study_estimation_window_keeps_other_events_windows():
    # Day 200's event window lies inside the second event's [t-250, t-20] window. It is not
    # masked, so the event is still estimated (the old masking left too few clean days).
    stock, bench, index = build_market(n=700, jumps={400: 0.05, 403: 0.05})
    sent = sent_frame(index, {400: (0.9, 3), 600: (0.5, 3)})

    first, second = run_event_study(stock, bench, sent, [])

    assert second.status == "ok"
    assert second.beta == pytest.approx(1.5, abs=0.1)  # 2 jumps in 231 days: small bias
    assert first.status == "ok"


def test_run_event_study_estimation_window_spans_250_sessions_back():
    # A jump at t-250 is inside the window, so it must bias beta; one at t-251 must not.
    stock, bench, index = build_market(n=700, jumps={350: 0.3})
    sent = sent_frame(index, {600: (0.9, 3)})
    (inside,) = run_event_study(stock, bench, sent, [])
    stock2, bench2, _ = build_market(n=700, jumps={349: 0.3})
    (outside,) = run_event_study(stock2, bench2, sent, [])

    assert inside.beta != pytest.approx(1.5, abs=TOL)
    assert outside.beta == pytest.approx(1.5, abs=TOL)


def test_run_event_study_estimation_window_upper_edge_is_t_minus_20():
    # A jump at t-20 is inside the window, so it must bias beta; one at t-19 must not.
    stock, bench, index = build_market(n=700, jumps={580: 0.3})
    sent = sent_frame(index, {600: (0.9, 3)})
    (inside,) = run_event_study(stock, bench, sent, [])
    stock2, bench2, _ = build_market(n=700, jumps={581: 0.3})
    (outside,) = run_event_study(stock2, bench2, sent, [])

    assert inside.beta != pytest.approx(1.5, abs=TOL)
    assert outside.beta == pytest.approx(1.5, abs=TOL)


def test_run_event_study_every_six_sessions_news_is_mostly_evaluated():
    # Regression: masking every event's [0, +5] window left no clean days on heavily covered
    # stocks, so almost all events were insufficient_estimation.
    stock, bench, index = build_market(n=780)
    sent = sent_frame(index, dict.fromkeys(range(260, 780, 6), (0.5, 4)))

    results = run_event_study(stock, bench, sent, [])

    ok = sum(1 for r in results if r.status == "ok")
    assert len(results) > 80
    assert ok / len(results) >= 0.9


def test_run_event_study_future_bars_and_news_never_change_earlier_event():
    stock, bench, index = build_market(n=700, jumps={450: 0.02})
    sent = sent_frame(index, dict.fromkeys(range(300, 500, 6), (0.5, 3)))
    base = run_event_study(stock, bench, sent, [index[300].date()])
    cut = index[480]  # events up to here have all their forward windows inside the data
    early = [r for r in base if r.date <= cut.date()]

    longer_stock, longer_bench, longer_index = build_market(n=900, jumps={450: 0.02, 600: -0.1})
    more = sent_frame(longer_index, dict.fromkeys(range(300, 800, 6), (0.5, 3)))
    earnings = [index[300].date(), longer_index[650].date()]
    redo = run_event_study(longer_stock, longer_bench, more, earnings)
    redo_early = [r for r in redo if r.date <= cut.date()]

    assert early
    assert redo_early == early


def test_run_event_study_pre_event_car_captures_run_up():
    stock, bench, index = build_market(jumps={196: 0.01, 199: 0.02})
    sent = sent_frame(index, {200: (0.9, 3)})

    (res,) = run_event_study(stock, bench, sent, [])

    assert res.car_pre_5 == pytest.approx(0.03, abs=TOL)
    assert res.car_0_5 == pytest.approx(0.0, abs=TOL)


def test_run_event_study_event_too_close_to_start_is_insufficient():
    stock, bench, index = build_market()
    sent = sent_frame(index, {50: (0.9, 3), 200: (0.5, 2)})

    early, ok = run_event_study(stock, bench, sent, [])

    assert early.status == "insufficient_estimation"
    assert (early.alpha, early.beta) == (None, None)
    assert early.car_0_0 is early.car_0_1 is early.car_0_5 is early.car_pre_5 is None
    assert ok.status == "ok"


def test_run_event_study_requires_min_estimation_observations():
    stock, bench, index = build_market()
    # Position 80 -> estimation positions 1..60 = exactly 60 observations.
    sent = sent_frame(index, {80: (0.9, 3), 79: (0.1, 1)})
    (at_limit,) = run_event_study(stock, bench, sent.iloc[[1]], [])
    assert at_limit.status == "ok"
    # One session earlier gives 59 observations.
    (below,) = run_event_study(stock, bench, sent.iloc[[0]], [])
    assert below.status == "insufficient_estimation"


def test_run_event_study_only_earnings_sessions_reduce_observation_count():
    stock, bench, index = build_market()
    sent = sent_frame(index, {80: (0.9, 3), 105: (0.8, 3)})
    # Event 105 estimates on positions 1..85 (85 obs). Event 80's window is NOT masked, but
    # earnings at 50 masks positions 49..51 (3 obs), leaving 82.
    earn = [index[50].date()]
    ok = run_event_study(stock, bench, sent, earn, min_est_obs=82)
    short = run_event_study(stock, bench, sent, earn, min_est_obs=83)
    assert ok[1].status == "ok"
    assert short[1].status == "insufficient_estimation"


def test_run_event_study_flat_benchmark_is_insufficient():
    stock, _, index = build_market()
    flat = pd.Series(100.0, index=index)
    sent = sent_frame(index, {200: (0.9, 3)})

    (res,) = run_event_study(stock, flat, sent, [])

    assert res.status == "insufficient_estimation"


def test_run_event_study_window_past_end_is_none():
    stock, bench, index = build_market()
    sent = sent_frame(index, {397: (0.9, 3)})

    (res,) = run_event_study(stock, bench, sent, [])

    assert res.status == "ok"
    assert res.car_0_0 is not None
    assert res.car_0_1 is not None  # positions 397, 398
    assert res.car_0_5 is None  # would need 402
    assert res.car_pre_5 is not None


def test_run_event_study_last_day_event_has_no_forward_cars():
    stock, bench, index = build_market()
    sent = sent_frame(index, {399: (0.9, 3)})

    (res,) = run_event_study(stock, bench, sent, [])

    assert res.car_0_0 is not None
    assert res.car_0_1 is None


def test_run_event_study_pre_window_before_first_return_is_none():
    stock, bench, index = build_market()
    sent = sent_frame(index, {5: (0.9, 3)})

    (res,) = run_event_study(stock, bench, sent, [], est_window=(150, 2), min_est_obs=3)

    assert res.status == "ok"
    assert res.car_pre_5 is None  # needs positions 0..4 but position 0 has no return
    assert res.car_0_5 is not None


def test_run_event_study_clustered_news_yields_single_event_per_cluster():
    stock, bench, index = build_market()
    # News every day for ten days around 200: only one event may be taken per 11-day block.
    rows = dict.fromkeys(range(195, 205), (0.5, 2))
    rows[200] = (0.9, 5)
    sent = sent_frame(index, rows)

    res = run_event_study(stock, bench, sent, [])

    dates = [r.date for r in res]
    assert index[200].date() in dates
    positions = [index.get_loc(pd.Timestamp(d)) for d in dates]
    assert all(b - a > 5 for a, b in itertools.pairwise(positions))
    assert len(res) < 10


def test_run_event_study_flags_earnings_within_five_sessions():
    stock, bench, index = build_market()
    sent = sent_frame(index, {200: (0.9, 3), 250: (0.8, 3), 300: (0.7, 3), 350: (0.6, 3)})
    earnings = [
        index[201].date(),  # one after event 200 -> near
        index[243].date(),  # seven before event 250 -> not near
        index[295].date(),  # five before event 300 -> near (boundary)
        index[356].date(),  # six after event 350 -> not near (boundary)
    ]

    res = run_event_study(stock, bench, sent, earnings)

    assert [r.near_earnings for r in res] == [True, False, True, False]


def test_run_event_study_masks_earnings_sessions_out_of_estimation_window():
    # A +20% earnings-day jump inside the estimation window would bias beta if it were kept.
    stock, bench, index = build_market(jumps={100: 0.2})
    sent = sent_frame(index, {200: (0.9, 3)})

    (res,) = run_event_study(stock, bench, sent, [index[100].date()])

    assert res.beta == pytest.approx(1.5, abs=TOL)
    assert res.alpha == pytest.approx(0.0002, abs=TOL)


def test_run_event_study_masks_day_after_earnings_too():
    stock, bench, index = build_market(jumps={101: -0.2})
    sent = sent_frame(index, {200: (0.9, 3)})

    (res,) = run_event_study(stock, bench, sent, [index[100].date()])

    assert res.beta == pytest.approx(1.5, abs=TOL)


def test_run_event_study_maps_weekend_earnings_to_next_session():
    stock, bench, index = build_market()
    friday = next(p for p in range(200, 260) if index[p].weekday() == 4)
    saturday = (index[friday] + pd.Timedelta(days=1)).date()  # Saturday -> maps to Monday
    sent = sent_frame(index, {friday + 1: (0.9, 3)})  # the Monday, distance 0

    (res,) = run_event_study(stock, bench, sent, [saturday])

    assert res.near_earnings is True


def test_run_event_study_ignores_earnings_after_data_end():
    stock, bench, index = build_market()
    sent = sent_frame(index, {399: (0.9, 3)})

    (res,) = run_event_study(stock, bench, sent, [date(2035, 1, 1)])

    assert res.near_earnings is False


def test_run_event_study_inner_joins_misaligned_price_dates():
    stock, bench, index = build_market()
    extra = pd.Series([1.0], index=[index[0] - pd.Timedelta(days=3)])
    stock_extra = pd.concat([extra, stock])
    sent = sent_frame(index, {200: (0.9, 3)})

    (res,) = run_event_study(stock_extra, bench, sent, [])

    assert res.beta == pytest.approx(1.5, abs=TOL)


def test_run_event_study_ignores_news_on_dates_without_prices():
    stock, bench, index = build_market()
    sent = sent_frame(index, {200: (0.9, 3)})
    sent.loc[pd.Timestamp("2035-01-01")] = (0.9, 3, 0.9)

    res = run_event_study(stock, bench, sent, [])

    assert [r.date for r in res] == [index[200].date()]


def test_run_event_study_empty_news_returns_empty():
    stock, bench, index = build_market()
    assert run_event_study(stock, bench, sent_frame(index, {}), []) == []


# --- select_events ---------------------------------------------------------------------


def _index(n: int = 100) -> pd.DatetimeIndex:
    return pd.bdate_range("2023-01-02", periods=n)


def test_select_events_greedy_by_salience_with_exclusion_zone():
    idx = _index()
    # salience: 10 -> 1.25, 12 -> 0.69, 16 -> 0.55, 17 -> 0.66, 30 -> 0.07
    sent = sent_frame(idx, {10: (0.9, 3), 12: (0.5, 3), 16: (0.4, 3), 17: (0.6, 2), 30: (0.1, 1)})

    picks = select_events(sent, idx)

    assert [idx.get_loc(p) for p in picks] == [10, 17, 30]


def test_select_events_boundary_distance_five_excluded_six_allowed():
    idx = _index()
    sent = sent_frame(idx, {10: (0.9, 3), 15: (0.5, 3), 16: (0.4, 3)})

    picks = select_events(sent, idx)

    assert [idx.get_loc(p) for p in picks] == [10, 16]


def test_select_events_result_is_sorted_by_date_not_salience():
    idx = _index()
    sent = sent_frame(idx, {50: (0.2, 1), 10: (0.9, 5)})

    picks = select_events(sent, idx)

    assert [idx.get_loc(p) for p in picks] == [10, 50]


def test_select_events_custom_exclusion_and_tie_break_by_date():
    idx = _index()
    sent = sent_frame(idx, {20: (0.5, 2), 22: (0.5, 2)})

    assert [idx.get_loc(p) for p in select_events(sent, idx, exclusion=1)] == [20, 22]
    assert [idx.get_loc(p) for p in select_events(sent, idx, exclusion=5)] == [20]


def test_select_events_negative_and_positive_sentiment_rank_by_magnitude():
    idx = _index()
    sent = sent_frame(idx, {20: (-0.9, 2), 22: (0.5, 2)})

    assert [idx.get_loc(p) for p in select_events(sent, idx)] == [20]


def test_select_events_empty_frame_returns_empty():
    idx = _index()
    assert select_events(sent_frame(idx, {}), idx) == []


def test_run_event_study_event_before_estimation_window_exists_is_insufficient():
    stock, bench, index = build_market()
    sent = sent_frame(index, {10: (0.9, 3)})

    (res,) = run_event_study(stock, bench, sent, [])

    assert res.status == "insufficient_estimation"


def test_run_event_study_window_with_non_finite_return_is_none():
    stock, bench, index = build_market()
    stock.iloc[203] = 0.0  # return at 203 is -100%, return at 204 divides by zero
    sent = sent_frame(index, {200: (0.9, 3)})

    (res,) = run_event_study(stock, bench, sent, [])

    assert res.car_0_1 is not None
    assert res.car_0_5 is None


def test_select_events_chain_is_causal_so_later_news_cannot_change_earlier_picks():
    idx = _index(120)
    # A 20-day chain with spacing <= 5 and rising salience: global greedy would favour the end.
    chain = {10: (0.2, 1), 14: (0.3, 1), 18: (0.4, 1), 22: (0.5, 1), 26: (0.6, 1), 30: (0.7, 1)}
    later = {**chain, 33: (0.95, 9), 36: (0.99, 9), 60: (0.5, 2)}

    short = [idx.get_loc(p) for p in select_events(sent_frame(idx, chain), idx)]
    full = [idx.get_loc(p) for p in select_events(sent_frame(idx, later), idx)]

    assert short == [14, 26]  # windows [10,15] and [22,27]; 30 is inside 26's exclusion
    assert full[:2] == short  # appended news only adds events after the closed windows
    assert full[2:] == [36, 60]


def test_select_events_picks_peak_of_each_bounded_window_and_keeps_windows_disjoint():
    idx = _index(120)
    sent = sent_frame(idx, {10: (0.2, 1), 14: (0.3, 1), 18: (0.4, 1), 22: (0.5, 1), 26: (0.6, 1)})

    picks = [idx.get_loc(p) for p in select_events(sent, idx)]

    # Window [10,15] -> 14; next candidate must be > 19: window [22,27] -> 26.
    assert picks == [14, 26]
    assert all(b - a > 5 for a, b in itertools.pairwise(picks))


def test_select_events_ignores_sessions_missing_from_trading_index():
    idx = _index(60)
    sent = sent_frame(idx, {10: (0.9, 3), 20: (0.5, 2)})
    sent.index = pd.DatetimeIndex([idx[10], pd.Timestamp("2023-02-04")])  # a Saturday

    picks = select_events(sent, idx)

    assert [idx.get_loc(p) for p in picks] == [10]
