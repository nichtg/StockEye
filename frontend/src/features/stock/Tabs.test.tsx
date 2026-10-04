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
    expect(screen.getByText('3.3% above its usual market-linked move')).toBeInTheDocument();
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
