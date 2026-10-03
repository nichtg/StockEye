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
    for r in res:
        assert r.beta == pytest.approx(1.5, abs=TOL)
        assert r.alpha == pytest.approx(0.0002, abs=TOL)
    assert first.car_0_0 == pytest.approx(0.03, abs=TOL)
    assert first.car_0_1 == pytest.approx(0.02, abs=TOL)  # 0.03 - 0.01
    assert first.car_0_5 == pytest.approx(0.02, abs=TOL)
    assert first.car_pre_5 == pytest.approx(0.0, abs=TOL)
    assert second.car_0_0 == pytest.approx(-0.02, abs=TOL)
    assert second.car_0_5 == pytest.approx(-0.02, abs=TOL)
    assert first.sentiment == 0.8
    assert first.article_count == 3


def test_run_event_study_estimation_window_skips_earlier_event_windows():
    # The second event's window [150, 280] contains day 200's jumps. If they were not
    # excluded, beta would be badly biased; exact recovery proves they are skipped.
    stock, bench, index = build_market(jumps={200: 0.05, 203: 0.05, 300: 0.01})
    sent = sent_frame(index, {200: (0.9, 3), 300: (0.5, 3)})

    second = run_event_study(stock, bench, sent, [])[1]

    assert second.beta == pytest.approx(1.5, abs=TOL)


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


def test_run_event_study_excluded_event_window_observations_do_not_count():
    stock, bench, index = build_market()
    sent = sent_frame(index, {80: (0.9, 3), 105: (0.8, 3)})
    # Event 105 estimates on positions 1..85 (85 obs) minus event 80's window 80..85 (6) = 79.
    ok = run_event_study(stock, bench, sent, [], min_est_obs=79)
    short = run_event_study(stock, bench, sent, [], min_est_obs=80)
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


def test_run_event_study_flags_earnings_within_one_session():
    stock, bench, index = build_market()
    sent = sent_frame(index, {200: (0.9, 3), 250: (0.8, 3), 300: (0.7, 3), 350: (0.6, 3)})
    earnings = [
        index[201].date(),  # next session -> within +/-1
        index[248].date(),  # two sessions before event 250 -> not near
        index[299].date(),  # one session before -> near
    ]

    res = run_event_study(stock, bench, sent, earnings)

    assert [r.near_earnings for r in res] == [True, False, True, False]


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
