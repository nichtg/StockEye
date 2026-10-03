import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { stubFetch } from '../../test/mockApi';
import { renderApp } from '../../test/render';
import { macroFixture, technicalFixture } from '../../test/fixtures';
import { MacroTab } from './MacroTab';
import { TechnicalTab } from './TechnicalTab';
import { patternSentence, wilsonInterval } from './technicalText';
import { MACRO_POLL_MS } from './useStockData';

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

describe('Macro tab', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('polls while news is being collected and stops when done', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let calls = 0;
    stubFetch((req) => {
      if (req.path !== '/stocks/AAPL/macro') return undefined;
      calls += 1;
      const done = calls >= 3;
      return {
        body: macroFixture({
          ingestion: { months_done: done ? 24 : calls * 8, months_total: 24, in_progress: !done },
        }),
      };
    });
    renderApp(<MacroTab symbol="AAPL" exchange="US" />);

    expect(await screen.findByText('Collecting news: 8 of 24 months')).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(MACRO_POLL_MS + 100);
    });
    expect(await screen.findByText('Collecting news: 16 of 24 months')).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(MACRO_POLL_MS + 100);
    });
    await waitFor(() => {
      expect(screen.queryByText(/Collecting news/)).not.toBeInTheDocument();
    });
    const before = calls;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(MACRO_POLL_MS * 3);
    });
    expect(calls).toBe(before);
  });

  it('shows findings with a reliability chip, and the p-value only inside Details', async () => {
    stubFetch((req) => (req.path === '/stocks/AAPL/macro' ? { body: macroFixture() } : undefined));
    const user = userEvent.setup();
    const { container } = renderApp(<MacroTab symbol="AAPL" exchange="US" />);

    expect(
      await screen.findByText('News over the last 30 days is more positive than usual.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Weak evidence')).toBeInTheDocument();
    expect(screen.getByText(/A pattern this strong would appear by chance/)).toBeInTheDocument();
    expect(screen.getByText('3.3% better than expected')).toBeInTheDocument();
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
