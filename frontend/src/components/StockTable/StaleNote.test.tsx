import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { OverviewRow } from '../../api/types';
import { StaleNote } from './StaleNote';

function row(over: Partial<OverviewRow>): OverviewRow {
  return {
    symbol: 'AAPL',
    name: 'Apple',
    exchange: 'US',
    currency: 'USD',
    last_price: 1,
    change_1w_pct: 0,
    sparkline: [],
    lean: null,
    country: null,
    sector: null,
    market_cap: null,
    status: 'stale',
    status_reason: null,
    ...over,
  };
}

describe('StaleNote', () => {
  it('shows the time when the price is from today', () => {
    const at = new Date();
    at.setHours(15, 58, 0, 0);
    render(<StaleNote locale="en-US" row={row({ status_as_of: at.toISOString() })} />);
    expect(
      screen.getByRole('button', { name: "Price as of 3:58 PM, couldn't refresh" }),
    ).toHaveTextContent('As of 3:58 PM');
  });

  it('shows the date when the price is older', () => {
    const at = new Date();
    at.setDate(at.getDate() - 3);
    const expected = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' }).format(
      at,
    );
    render(<StaleNote locale="en-US" row={row({ status_as_of: at.toISOString() })} />);
    expect(screen.getByRole('button')).toHaveTextContent(`As of ${expected}`);
  });

  it('falls back to "Last saved price" without a timestamp', () => {
    render(<StaleNote row={row({})} />);
    expect(screen.getByRole('button')).toHaveTextContent('Last saved price');
  });

  it('keeps "Partial data" for partial rows', () => {
    render(<StaleNote row={row({ status: 'partial' })} />);
    expect(screen.getByRole('button')).toHaveTextContent('Partial data');
  });

  it('shows "Last saved price" for an invalid timestamp', () => {
    render(<StaleNote row={row({ status_as_of: 'garbage' })} />);
    expect(screen.getByRole('button')).toHaveTextContent('Last saved price');
  });

  it('opens the reason on hover and closes it on Escape without reopening', async () => {
    const user = userEvent.setup();
    render(<StaleNote row={row({ status_reason: 'Yahoo timed out.' })} />);
    await user.hover(screen.getByRole('button'));
    expect(
      await screen.findByText(
        /Couldn't refresh just now; showing the last saved price\. Yahoo timed out\./,
      ),
    ).toBeInTheDocument();
    await user.keyboard('{Escape}');
    await waitFor(() => {
      expect(screen.queryByText(/Couldn't refresh just now/)).not.toBeInTheDocument();
    });
  });

  it('stays open when clicked after hover', async () => {
    const user = userEvent.setup();
    render(<StaleNote row={row({})} />);
    await user.hover(screen.getByRole('button'));
    expect(await screen.findByText(/Couldn't refresh just now/)).toBeInTheDocument();
    await user.click(screen.getByRole('button'));
    expect(screen.getByText(/Couldn't refresh just now/)).toBeInTheDocument();
  });
});
