import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { stubFetch } from '../../test/mockApi';
import { renderApp } from '../../test/render';
import { macroFixture, technicalFixture } from '../../test/fixtures';
import { MacroTab } from './MacroTab';
import { TechnicalTab } from './TechnicalTab';
import { patternSentence, wilsonInterval } from './technicalText';

describe('Technical tab', () => {
  it('explains reliability in plain language and never shows n= or p=', async () => {
    stubFetch((req) =>
      req.path === '/stocks/AAPL/technical' ? { body: technicalFixture } : undefined,
    );
    const { container } = renderApp(<TechnicalTab symbol="AAPL" exchange="US" />);

    expect(await screen.findByText('Bullish', { selector: 'strong' })).toBeInTheDocument();
    expect(screen.getByText('$317.96 to $349.42')).toBeInTheDocument();
    expect(
      screen.getByText(
        'Seen 12 times in the past 3 years; price was higher a week later 9 of 12 times (75%), versus 55% for a typical week.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('Only seen 4 times; not enough history to judge.')).toBeInTheDocument();
    // The zero-weight signal is dimmed and says why it does not count.
    expect(screen.getByText('Not counted in the outlook.')).toBeInTheDocument();

    const text = container.textContent;
    expect(text).not.toMatch(/\bn=/);
    expect(text).not.toMatch(/\bp=/);
    expect(text).not.toContain('backend sentence');
  });

  it('keeps the statistics collapsed until asked', async () => {
    stubFetch((req) =>
      req.path === '/stocks/AAPL/technical' ? { body: technicalFixture } : undefined,
    );
    const user = userEvent.setup();
    renderApp(<TechnicalTab symbol="AAPL" exchange="US" />);
    await screen.findByText('Bullish', { selector: 'strong' });
    await user.click(screen.getByRole('button', { name: 'Show statistics' }));
    const table = await screen.findByRole('table', { name: 'Pattern statistics' });
    expect(within(table).getByText('Bullish engulfing')).toBeInTheDocument();
    expect(within(table).getAllByText('75%').length).toBeGreaterThan(0);
  });

  it('phrases helpers sensibly', () => {
    expect(patternSentence(null, 'bullish')).toMatch(/nothing to judge/);
    const [lo, hi] = wilsonInterval(9, 12);
    expect(lo).toBeGreaterThan(0.45);
    expect(hi).toBeLessThan(0.95);
  });
});

describe('Technical tab: latest pattern', () => {
  function renderWith(latestAgo: number | null, recent: boolean) {
    stubFetch((req) =>
      req.path === '/stocks/AAPL/technical'
        ? {
            body: {
              ...technicalFixture,
              recent_patterns: recent ? technicalFixture.recent_patterns : [],
              latest_pattern:
                latestAgo === null
                  ? null
                  : {
                      date: '2026-09-23',
                      pattern: 'bearish_engulfing',
                      label: 'Bearish engulfing',
                      bias: 'bearish',
                      sessions_ago: latestAgo,
                    },
            },
          }
        : undefined,
    );
    renderApp(<TechnicalTab symbol="AAPL" exchange="US" />);
  }

  it('says when the most recent pattern was, with a plural count', async () => {
    renderWith(6, false);
    const line = await screen.findByText(/No patterns in the last 3 trading days\./);
    expect(line).toHaveTextContent(
      'The most recent was a bearish engulfing pattern on Sep 23, 2026 (6 trading days ago), too old to count in this week’s outlook.',
    );
    expect(screen.getByRole('button', { name: 'What is bearish engulfing?' })).toBeInTheDocument();
  });

  it('uses the singular for one day', async () => {
    renderWith(1, false);
    expect(await screen.findByText(/\(1 trading day ago\)/)).toBeInTheDocument();
  });

  it('says nothing about an older pattern when there are recent ones', async () => {
    renderWith(6, true);
    await screen.findByText('Bullish', { selector: 'strong' });
    expect(screen.queryByText(/The most recent was/)).not.toBeInTheDocument();
    expect(screen.queryByText(/No patterns in the last/)).not.toBeInTheDocument();
  });
});

describe('Macro tab', () => {
  it('shows the Preliminary chip and the progress bar while news is being collected', async () => {
    stubFetch((req) =>
      req.path === '/stocks/AAPL/macro'
        ? {
            body: macroFixture({
              ingestion: { months_done: 8, months_total: 24, in_progress: true },
            }),
          }
        : undefined,
    );
    renderApp(<MacroTab symbol="AAPL" exchange="US" />);
    expect(await screen.findByText('Collecting news: 8 of 24 months')).toBeInTheDocument();
    expect(screen.getByText('Preliminary')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'What is Preliminary?' })).toBeInTheDocument();
    expect(screen.queryByText(/News complete/)).not.toBeInTheDocument();
  });

  it("prefers the page poller's live progress over the macro answer's copy", async () => {
    stubFetch((req) => (req.path === '/stocks/AAPL/macro' ? { body: macroFixture() } : undefined));
    renderApp(
      <MacroTab
        symbol="AAPL"
        exchange="US"
        news={{ months_done: 16, months_total: 24, in_progress: true, status: { state: 'ok' } }}
      />,
    );
    expect(await screen.findByText('Collecting news: 16 of 24 months')).toBeInTheDocument();
    expect(screen.getByText('Preliminary')).toBeInTheDocument();
  });

  it('replaces the bar with a quiet complete line, and no chip, once done', async () => {
    stubFetch((req) => (req.path === '/stocks/AAPL/macro' ? { body: macroFixture() } : undefined));
    renderApp(<MacroTab symbol="AAPL" exchange="US" />);
    expect(await screen.findByText(/News complete: 24 months · updated .+/)).toBeInTheDocument();
    expect(screen.queryByText('Preliminary')).not.toBeInTheDocument();
    expect(screen.queryByText(/Collecting news/)).not.toBeInTheDocument();
  });

  it('labels each reliability value plainly, with no good-or-bad wording', async () => {
    const base = macroFixture();
    const report = base.report;
    if (!report) throw new Error('fixture has no report');
    const finding = (reliability: 'clear_effect' | 'possible_effect' | 'no_clear_effect') => ({
      text: `Finding for ${reliability}.`,
      based_on_events: 30,
      reliability,
      p_value: 0.2,
    });
    stubFetch((req) =>
      req.path === '/stocks/AAPL/macro'
        ? {
            body: {
              ...base,
              report: {
                ...report,
                primary_findings: [
                  finding('clear_effect'),
                  finding('possible_effect'),
                  finding('no_clear_effect'),
                ],
              },
            },
          }
        : undefined,
    );
    renderApp(<MacroTab symbol="AAPL" exchange="US" />);
    expect(await screen.findByText('Clear news effect')).toBeInTheDocument();
    expect(screen.getByText('Possible news effect')).toBeInTheDocument();
    expect(screen.getByText('No clear news effect')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'What is News effect?' })).toHaveLength(3);
  });

  it('shows the earnings note under the findings only when there is one', async () => {
    const note = 'This effect comes mostly from news around earnings releases.';
    const base = macroFixture();
    const report = base.report;
    if (!report) throw new Error('fixture has no report');
    stubFetch((req) =>
      req.path === '/stocks/AAPL/macro'
        ? { body: { ...base, report: { ...report, earnings_note: note } } }
        : undefined,
    );
    const first = renderApp(<MacroTab symbol="AAPL" exchange="US" />);
    expect(await screen.findByText(note)).toBeInTheDocument();
    first.unmount();

    stubFetch((req) => (req.path === '/stocks/AAPL/macro' ? { body: macroFixture() } : undefined));
    renderApp(<MacroTab symbol="AAPL" exchange="US" />);
    await screen.findByText('Possible news effect');
    expect(screen.queryByText(note)).not.toBeInTheDocument();
  });

  it('shows findings with a reliability chip, and the p-value only inside Details', async () => {
    stubFetch((req) => (req.path === '/stocks/AAPL/macro' ? { body: macroFixture() } : undefined));
    const user = userEvent.setup();
    const { container } = renderApp(<MacroTab symbol="AAPL" exchange="US" />);

    expect(
      await screen.findByText('News over the last 30 days is more positive than usual.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Possible news effect')).toBeInTheDocument();
    expect(screen.getByText(/A pattern this strong would appear by chance/)).toBeInTheDocument();
    expect(screen.getByText('3.3%')).toBeInTheDocument();
    expect(screen.getByText('above its usual market‑linked move')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Apple to Bring TV+ to Android' })).toHaveAttribute(
      'target',
      '_blank',
    );

    expect(container.textContent).not.toMatch(/p-value/i);
    expect(container.textContent).not.toMatch(/\bn=|\bp=/);

    await user.click(screen.getByRole('button', { name: 'Details' }));
    const details = await screen.findByRole('region', { name: 'Details' }).catch(() => null);
    const scope = details ?? container;
    expect((await within(scope).findAllByText('p-value')).length).toBeGreaterThan(0);
    expect(screen.getByText('0.012')).toBeInTheDocument();
  });

  it('captions the scope of the findings and labels the secondary scope in Details', async () => {
    const base = macroFixture();
    const report = base.report;
    if (!report) throw new Error('fixture has no report');
    stubFetch((req) =>
      req.path === '/stocks/AAPL/macro'
        ? {
            body: {
              ...base,
              report: {
                ...report,
                primary_scope: 'excluding_earnings',
                secondary_scope: 'all_events',
                secondary_findings: [
                  {
                    text: 'Across every day, moves were similar.',
                    based_on_events: 40,
                    reliability: null,
                    p_value: null,
                  },
                ],
              },
            },
          }
        : undefined,
    );
    const user = userEvent.setup();
    renderApp(<MacroTab symbol="AAPL" exchange="US" />);
    expect(await screen.findByText(/Excluding days near/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Details' }));
    expect((await screen.findAllByText('All news days')).length).toBeGreaterThan(0);
  });

  it('shows the new-stock budget reason as a calm notice, not an error', async () => {
    const reason = 'Daily limit for analysing new stocks reached; try again tomorrow.';
    const base = macroFixture();
    stubFetch((req) =>
      req.path === '/stocks/AAPL/macro'
        ? {
            body: {
              ...base,
              report: null,
              data_status: {
                ...base.data_status,
                news: { state: 'unavailable', reason, as_of: null },
              },
            },
          }
        : undefined,
    );
    renderApp(<MacroTab symbol="AAPL" exchange="US" />);
    const notice = (await screen.findByText(reason)).closest('[role="status"]');
    expect(notice).not.toBeNull();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows the rate limit inline with a retry button', async () => {
    stubFetch(() => ({ status: 429, body: '<html>429</html>' }));
    renderApp(<MacroTab symbol="AAPL" exchange="US" />);
    expect(
      await screen.findByText('Too many requests. Please wait a minute and try again.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('says so when there is nothing to analyse', async () => {
    stubFetch((req) =>
      req.path === '/stocks/AAPL/macro'
        ? {
            body: macroFixture({
              report: null,
              ingestion: { months_done: 0, months_total: 24, in_progress: false },
            }),
          }
        : undefined,
    );
    renderApp(<MacroTab symbol="AAPL" exchange="US" />);
    expect(
      await screen.findByText('Not enough news yet to analyse this stock.'),
    ).toBeInTheDocument();
  });
});

describe('Macro tab period and counts', () => {
  const bucket = (bucket: 'positive' | 'neutral' | 'negative', n: number) => ({
    bucket,
    n,
    mean_car_0_1: 0.001,
    median_car_0_1: 0.001,
    n_car_0_5: n,
    mean_car_0_5: null,
    median_car_0_5: null,
    mean_car_pre_5: null,
    t: null,
    p_value: null,
    label: null,
  });

  function withStats(
    mutate: (r: NonNullable<ReturnType<typeof macroFixture>['report']>) => void,
  ): ReturnType<typeof macroFixture> {
    const data = macroFixture();
    if (!data.report) throw new Error('fixture has no report');
    mutate(data.report);
    return data;
  }

  const stats = (n_used: number, first: string | null, last: string | null, b = {}) => ({
    ...macroFixture().report!.stats_all,
    n_used,
    first_event: first,
    last_event: last,
    buckets: b,
  });

  function show(data: ReturnType<typeof macroFixture>) {
    stubFetch((req) => (req.path === '/stocks/AAPL/macro' ? { body: data } : undefined));
    return renderApp(<MacroTab symbol="AAPL" exchange="US" />);
  }

  const isLine = (re: RegExp) => (_: string, el: Element | null) =>
    el?.tagName === 'P' && re.test(el.textContent);
  const countsLine = (re: RegExp) => screen.getByText(isLine(re));
  const findCounts = (re: RegExp) => screen.findByText(isLine(re));

  const PERIOD =
    'Based on news from Oct 2024 to Oct 2026. Each result compares the stock’s move on a news day and the next trading day with what the market predicted.';

  it('says which months the findings cover and how the events split', async () => {
    show(
      withStats((r) => {
        r.stats_ex_earnings = stats(29, '2024-10-01', '2026-10-02', {
          positive: bucket('positive', 17),
          neutral: bucket('neutral', 7),
          negative: bucket('negative', 5),
        });
      }),
    );
    const period = await screen.findByText(/Based on news from/);
    expect(period.textContent).toBe(PERIOD);
    expect(
      within(period).getByRole('button', { name: 'What is Market-adjusted move?' }),
    ).toBeInTheDocument();
    const counts = countsLine(/^29 news days studied:/);
    expect(counts.textContent).toBe('29 news days studied: 17 positive, 7 neutral, 5 negative');
    for (const name of ['Positive news day', 'Neutral news day', 'Negative news day']) {
      expect(within(counts).getByRole('button', { name: `What is ${name}?` })).toBeInTheDocument();
    }
  });

  it('uses one month, the singular, and zero for a missing bucket', async () => {
    show(
      withStats((r) => {
        r.stats_ex_earnings = stats(1, '2026-10-02', '2026-10-20', {
          positive: bucket('positive', 1),
        });
      }),
    );
    expect((await screen.findByText(/Based on news from/)).textContent).toContain(
      'Based on news from Oct 2026. Each',
    );
    expect(countsLine(/^1 news day studied:/).textContent).toBe(
      '1 news day studied: 1 positive, 0 neutral, 0 negative',
    );
  });

  it('takes the numbers from the stats the primary scope names', async () => {
    show(
      withStats((r) => {
        r.primary_scope = 'all_events';
        r.stats_all = stats(40, '2023-03-01', '2026-02-01');
        r.stats_ex_earnings = stats(30, '2024-10-01', '2026-10-02');
      }),
    );
    expect(await findCounts(/^40 news days studied:/)).toBeInTheDocument();
    expect(screen.getByText(/Mar 2023 to Feb 2026/)).toBeInTheDocument();
    expect(screen.queryByText(/30 news days studied/)).not.toBeInTheDocument();
  });

  it('leaves out the period without both dates, and the counts for an empty scope', async () => {
    show(
      withStats((r) => {
        r.stats_ex_earnings = stats(0, null, '2026-10-02');
      }),
    );
    await screen.findByText('Possible news effect');
    expect(screen.queryByText(/Based on news from/)).not.toBeInTheDocument();
    expect(screen.queryByText(isLine(/^[0-9]+ news days? studied/))).not.toBeInTheDocument();
  });

  it('gives the secondary scope in Details its own period and counts', async () => {
    show(
      withStats((r) => {
        r.secondary_scope = 'all_events';
        r.secondary_findings = [
          {
            text: 'Across every day, moves were similar.',
            based_on_events: 40,
            reliability: null,
            p_value: null,
          },
        ];
        r.stats_ex_earnings = stats(30, '2024-10-01', '2026-10-02');
        r.stats_all = stats(40, '2023-03-01', '2026-02-01', { neutral: bucket('neutral', 40) });
      }),
    );
    const user = userEvent.setup();
    await findCounts(/^30 news days studied:/);
    await user.click(screen.getByRole('button', { name: 'Details' }));
    expect(await findCounts(/^40 news days studied:/)).toBeInTheDocument();
    expect(screen.getByText(/Mar 2023 to Feb 2026/)).toBeInTheDocument();
  });
});
