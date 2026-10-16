import { screen } from '@testing-library/react';
import { profileFixture, stockFixture } from '../../test/fixtures';
import { stubFetch } from '../../test/mockApi';
import { renderApp } from '../../test/render';
import { StockHeader } from './StockHeader';

function show(profile: Record<string, unknown>) {
  stubFetch((req) => {
    if (req.path === '/stocks/AAPL/profile') return { body: { ...profileFixture, ...profile } };
    if (req.path === '/watchlist') return { body: { symbols: [] } };
    return undefined;
  });
  renderApp(<StockHeader symbol="AAPL" stock={stockFixture} loading={false} statuses={[]} />);
}

describe('StockHeader industry chip', () => {
  it('shows the industry as one sentence-case chip, with no country', async () => {
    show({});
    expect(await screen.findByText('Consumer electronics')).toBeInTheDocument();
    expect(screen.queryByText(/headquartered/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/United States/)).not.toBeInTheDocument();
    // Sector moved to the About section; the header no longer shows it.
    expect(screen.queryByText('Technology')).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain('·');
  });

  it('handles Yahoo industries written as "X - Y"', async () => {
    show({ industry: 'Banks - Regional', country: 'Singapore' });
    expect(await screen.findByText('Regional banks')).toBeInTheDocument();
    expect(screen.queryByText(/Singapore/)).not.toBeInTheDocument();
  });

  it('shows no chip when the industry is unknown', async () => {
    show({ industry: null });
    // The row is reserved before the profile resolves, so nothing jumps.
    expect(screen.getByTestId('industry-row')).toBeInTheDocument();
    await screen.findByRole('button', { name: /watchlist/i });
    expect(screen.queryByText(/headquartered/i)).not.toBeInTheDocument();
    expect(screen.queryByText('Consumer electronics')).not.toBeInTheDocument();
    expect(screen.queryByTestId('industry-chip')).not.toBeInTheDocument();
    expect(screen.getByTestId('industry-row')).toBeInTheDocument();
  });
});
