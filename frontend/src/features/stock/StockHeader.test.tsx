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

describe('StockHeader profile line', () => {
  it('describes the company in one plain-English sentence', async () => {
    show({});
    expect(
      await screen.findByText('Consumer electronics, headquartered in the United States'),
    ).toBeInTheDocument();
    // Sector moved to the About section; the header no longer shows it.
    expect(screen.queryByText('Technology')).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain('·');
  });

  it('handles Yahoo industries written as "X - Y"', async () => {
    show({ industry: 'Banks - Regional', country: 'Singapore' });
    expect(
      await screen.findByText('Regional banks, headquartered in Singapore'),
    ).toBeInTheDocument();
  });

  it('shows only the part that is known', async () => {
    show({ industry: null });
    expect(await screen.findByText('Headquartered in the United States')).toBeInTheDocument();
  });

  it('renders nothing when neither is known', async () => {
    show({ industry: null, country: null });
    await screen.findByRole('button', { name: /watchlist/i });
    expect(screen.queryByText(/headquartered/i)).not.toBeInTheDocument();
    expect(screen.queryByText('Consumer Electronics')).not.toBeInTheDocument();
  });
});
