import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { macroFixture } from '../../../test/fixtures';
import { stubFetch } from '../../../test/mockApi';
import { renderApp } from '../../../test/render';
import { MacroTab } from '../MacroTab';
import { symmetricAxis } from './chartScale';

function show(data = macroFixture()) {
  stubFetch((req) => (req.path === '/stocks/AAPL/macro' ? { body: data } : undefined));
  return renderApp(<MacroTab symbol="AAPL" exchange="US" />);
}

describe('symmetricAxis', () => {
  it('is symmetric around zero, ends on a tick and covers the extent', () => {
    const { max, ticks } = symmetricAxis(2.4);
    expect(max).toBeGreaterThanOrEqual(2.4);
    expect(ticks[0]).toBe(-max);
    expect(ticks.at(-1)).toBe(max);
    expect(ticks).toContain(0);
  });

  it('falls back to a usable axis for no extent', () => {
    expect(symmetricAxis(0).max).toBeGreaterThan(0);
  });
});

describe('Verdict rows', () => {
  it('shows the value statement, each question, answer and detail', async () => {
    show();
    const list = await screen.findByRole('list', { name: 'Answers' });
    const items = within(list).getAllByRole('listitem');
    expect(items).toHaveLength(3);
    expect(
      screen.getByText(/Shows whether news days for this stock moved its price/),
    ).toBeVisible();
    expect(within(items[0]!).getByText('Does good news lift the price?')).toBeInTheDocument();
    expect(within(items[0]!).getByText('Not clearly')).toBeInTheDocument();
    expect(within(items[0]!).getByText(/across 21 days with positive news/)).toBeInTheDocument();
    expect(within(items[2]!).getByText('Possibly')).toBeInTheDocument();
  });

  it('draws the insufficient answer quieter than the others', async () => {
    show();
    const quiet = await screen.findByText('Not enough data', { selector: '.MuiChip-label' });
    const chip = quiet.closest('.MuiChip-root');
    expect(chip).toHaveAttribute('data-kind', 'insufficient');
    const other = screen.getByText('Possibly').closest('.MuiChip-root');
    expect(other).toHaveAttribute('data-kind', 'possible');
    expect(getComputedStyle(chip!).fontWeight).not.toBe(getComputedStyle(other!).fontWeight);
  });

  it('hides the answers and the chart when there are no verdicts', async () => {
    const data = macroFixture();
    if (!data.report) throw new Error('fixture has no report');
    data.report.verdicts = [];
    show(data);
    await screen.findByText('News over the last 30 days is more positive than usual.');
    expect(screen.queryByRole('list', { name: 'Answers' })).not.toBeInTheDocument();
    expect(screen.queryByRole('img', { name: /Average market-adjusted/ })).not.toBeInTheDocument();
  });
});

describe('Bucket chart', () => {
  it('draws a bar and whisker with a signed label for a tested bucket', async () => {
    show();
    const row = await screen.findByTestId('bucket-row-positive');
    expect(within(row).getByText('Positive news')).toBeInTheDocument();
    expect(within(row).getByText('21 days')).toBeInTheDocument();
    expect(within(row).getByText('+1.0%')).toBeInTheDocument();
    expect(screen.getByTestId('bucket-bar-positive')).toBeInTheDocument();
    expect(screen.getByTestId('bucket-whisker-positive')).toBeInTheDocument();
    // A fall gets the true minus, never colour alone.
    expect(within(screen.getByTestId('bucket-row-neutral')).getByText('−1.2%')).toBeInTheDocument();
  });

  it('says not enough data, with the count, instead of a bar for an untested bucket', async () => {
    show();
    const row = await screen.findByTestId('bucket-row-negative');
    expect(within(row).getByText('Not enough data (4 days; 10 needed)')).toBeInTheDocument();
    expect(screen.queryByTestId('bucket-bar-negative')).not.toBeInTheDocument();
  });

  it('fades a bar whose result could be chance and leaves a clear one solid', async () => {
    show();
    await screen.findByTestId('bucket-bar-positive');
    expect(screen.getByTestId('bucket-bar-positive')).toHaveAttribute('opacity', '0.4');
    expect(screen.getByTestId('bucket-bar-neutral')).toHaveAttribute('opacity', '1');
    expect(screen.getByText(/Faded: could be chance/)).toBeInTheDocument();
  });

  it('names the chart and repeats the numbers in a hidden table', async () => {
    show();
    const chart = await screen.findByRole('img', { name: /Average market-adjusted 2-day move/ });
    expect(chart.getAttribute('aria-label')).toContain('Positive news +1.0% (21 days)');
    expect(chart.getAttribute('aria-label')).toContain(
      'Negative news: Not enough data (4 days; 10 needed)',
    );
    const table = screen.getByRole('table', {
      name: 'Average market-adjusted 2-day move by type of news day',
    });
    const rows = within(table).getAllByRole('row');
    expect(
      within(rows[1]!)
        .getAllByRole('cell')
        .map((c) => c.textContent),
    ).toEqual(['Positive news', '21', '+1.0%', '−0.4% to +2.4%', 'Yes']);
    expect(within(rows[3]!).getByText('Not enough data (4 days; 10 needed)')).toBeInTheDocument();
  });

  it('explains the market-adjusted move with a help button', async () => {
    show();
    const buttons = await screen.findAllByRole('button', { name: 'What is Market-adjusted move?' });
    expect(buttons.some((b) => b.closest('p')?.textContent.includes('by type of news day'))).toBe(
      true,
    );
  });
});

describe('How this was worked out', () => {
  it('is collapsed by default, with the method and findings inside once opened', async () => {
    show();
    const user = userEvent.setup();
    const toggle = await screen.findByRole('button', { name: 'How this was worked out' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText(/Based on news from/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Across 34 news days studied/)).not.toBeInTheDocument();

    await user.click(toggle);
    expect(await screen.findByText(/Based on news from/)).toBeInTheDocument();
    expect(screen.getByText(/Across 34 news days studied/)).toBeInTheDocument();
    expect(screen.getByText(/would appear by chance about 4 in 100 times/)).toBeInTheDocument();
    expect(screen.getAllByText(/Excluding days near/).length).toBeGreaterThan(0);
  });

  it('keeps the empty state when there is nothing to analyse', async () => {
    show(macroFixture({ report: null }));
    expect(
      await screen.findByText('Not enough news yet to analyse this stock.'),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'How this was worked out' }),
    ).not.toBeInTheDocument();
  });
});
