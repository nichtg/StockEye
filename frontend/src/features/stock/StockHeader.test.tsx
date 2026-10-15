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
  it('shows sector, industry and country as separate items', async () => {
    show({});
    expect(await screen.findByText('Technology')).toBeInTheDocument();
    expect(screen.getByText('Consumer Electronics')).toBeInTheDocument();
    expect(screen.getByText('United States')).toBeInTheDocument();
    expect(document.body.textContent).not.toContain('·');
  });

  it('hides the items that are missing', async () => {
    show({ industry: null, country: null });
    expect(await screen.findByText('Technology')).toBeInTheDocument();
    expect(screen.queryByText('Consumer Electronics')).not.toBeInTheDocument();
    expect(screen.queryByText('United States')).not.toBeInTheDocument();
  });
});
