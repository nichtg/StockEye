import { screen } from '@testing-library/react';
import { useEffect } from 'react';
import { Route, Routes } from 'react-router';
import type { FullStatuses } from '../api/types';
import { stubFetch } from '../test/mockApi';
import { stockFixture } from '../test/fixtures';
import { renderApp } from '../test/render';
import StockPage from './StockPage';

const chartStatuses: FullStatuses = {
  prices: { state: 'stale', reason: 'Prices are 3 hours old.' },
  events: { state: 'partial', reason: 'Earnings dates are missing.' },
  news: { state: 'stale', reason: 'Chart copy of the news message.' },
  overall: { state: 'stale', reason: 'Prices are 3 hours old.' },
};

// The real chart needs a canvas; only the status it reports matters here.
vi.mock('../features/chart/StockChart', () => ({
  StockChart: ({ onStatus }: { onStatus: (s: FullStatuses) => void }) => {
    useEffect(() => {
      onStatus(chartStatuses);
    }, [onStatus]);
    return null;
  },
}));

describe('Stock page header status', () => {
  it('keeps price and events problems, and takes the news line from the live poller only', async () => {
    stubFetch((req) => {
      if (req.path === '/stocks/AAPL') return { body: stockFixture };
      if (req.path === '/stocks/AAPL/news') {
        return {
          body: {
            months_done: 8,
            months_total: 24,
            in_progress: true,
            status: { state: 'partial', reason: 'Collected 8 of 24 months of news so far.' },
          },
        };
      }
      return undefined;
    });
    renderApp(
      <Routes>
        <Route path="/stock/:symbol" element={<StockPage />} />
      </Routes>,
      { route: '/stock/AAPL' },
    );

    expect(
      await screen.findByText(/Collected 8 of 24 months of news so far\./),
    ).toBeInTheDocument();
    const line = screen.getByText(/Prices are 3 hours old\./);
    expect(line).toHaveTextContent('Earnings dates are missing.');
    expect(line).toHaveTextContent('Collected 8 of 24 months of news so far.');
    expect(line).not.toHaveTextContent('Chart copy of the news message.');
  });
});
