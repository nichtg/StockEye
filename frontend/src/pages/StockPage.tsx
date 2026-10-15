import Box from '@mui/material/Box';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import { useCallback, useState } from 'react';
import { useParams, useSearchParams } from 'react-router';
import { isApiError, userMessage } from '../api/errors';
import type { FullStatuses } from '../api/types';
import { ErrorState } from '../components/ErrorState';
import { StockNotFound } from '../components/StockNotFound';
import { StockChart } from '../features/chart/StockChart';
import { AboutCompany } from '../features/stock/AboutCompany';
import { MacroTab } from '../features/stock/MacroTab';
import { NewsTab } from '../features/stock/NewsTab';
import { StockHeader } from '../features/stock/StockHeader';
import { TechnicalTab } from '../features/stock/TechnicalTab';
import { useNewsProgress, useStock } from '../features/stock/useStockData';
import { useDocumentTitle } from '../hooks';
import { exchangeOfSymbol } from '../lib/exchange';

type TabKey = 'technical' | 'macro' | 'news';

function tabOf(value: string | null): TabKey {
  return value === 'macro' || value === 'news' ? value : 'technical';
}

export default function StockPage() {
  const { symbol: raw = '' } = useParams();
  const symbol = raw.toUpperCase();
  useDocumentTitle(symbol);
  const [params, setParams] = useSearchParams();
  const tab = tabOf(params.get('tab'));
  // Tagged with its symbol, so the previous symbol's freshness never shows under a new header.
  const [reported, setReported] = useState<{ symbol: string; status?: FullStatuses }>();
  const chartStatuses = reported?.symbol === symbol ? reported.status : undefined;
  const setChartStatus = useCallback(
    (status: FullStatuses | undefined) => {
      setReported({ symbol, status });
    },
    [symbol],
  );

  const stock = useStock(symbol);
  // On every tab, so opening a stock starts news collection. It is also the header's news line.
  const news = useNewsProgress(symbol);

  if (stock.isError && isApiError(stock.error) && stock.error.status === 404) {
    return <StockNotFound symbol={symbol} />;
  }
  if (stock.isError && !stock.data) {
    return (
      <ErrorState
        title={`We couldn’t load ${symbol}`}
        message={userMessage(stock.error)}
        onRetry={() => void stock.refetch()}
      />
    );
  }

  const exchange = stock.data?.exchange ?? exchangeOfSymbol(symbol);

  return (
    <Box>
      <StockHeader
        symbol={symbol}
        stock={stock.data}
        loading={stock.isPending}
        statuses={[
          stock.data?.data_status,
          chartStatuses?.prices,
          chartStatuses?.events,
          news.data?.status ?? chartStatuses?.news,
        ]}
      />

      <Box sx={{ mt: 4 }}>
        <StockChart symbol={symbol} stock={stock.data} onStatus={setChartStatus} />
      </Box>

      <Box sx={{ mt: { xs: 4, md: 5 } }}>
        <Tabs
          value={tab}
          aria-label="Analysis"
          onChange={(_e, value: TabKey) => {
            // Only the tab is touched: the chart's range and indicators live in the same URL.
            setParams(
              (previous) => {
                const next = new URLSearchParams(previous);
                if (value === 'technical') next.delete('tab');
                else next.set('tab', value);
                return next;
              },
              { replace: true },
            );
          }}
          // Three labels are wider than a phone: the track scrolls sideways instead of the page.
          variant="scrollable"
          scrollButtons={false}
          sx={{ mb: { xs: 4, md: 5 }, width: 'fit-content', maxWidth: '100%' }}
        >
          {/* aria-controls may only name a panel that exists, and only the active one is rendered. */}
          <Tab
            value="technical"
            label="Technical (1 week)"
            id="tab-technical"
            aria-controls={tab === 'technical' ? 'panel-technical' : undefined}
          />
          <Tab
            value="macro"
            label="Macro (2 years)"
            id="tab-macro"
            aria-controls={tab === 'macro' ? 'panel-macro' : undefined}
          />
          <Tab
            value="news"
            label="News (6 months)"
            id="tab-news"
            aria-controls={tab === 'news' ? 'panel-news' : undefined}
          />
        </Tabs>
        <Box
          role="tabpanel"
          id={`panel-${tab}`}
          aria-labelledby={`tab-${tab}`}
          sx={{ minHeight: 240 }}
        >
          {tab === 'technical' ? (
            <TechnicalTab symbol={symbol} exchange={exchange} />
          ) : tab === 'macro' ? (
            <MacroTab symbol={symbol} exchange={exchange} news={news.data} />
          ) : (
            <NewsTab symbol={symbol} name={stock.data?.name} exchange={exchange} news={news.data} />
          )}
        </Box>
      </Box>

      <Box sx={{ mt: 6 }}>
        <AboutCompany
          symbol={symbol}
          name={stock.data?.name}
          exchange={exchange}
          currency={stock.data?.currency ?? 'USD'}
        />
      </Box>
    </Box>
  );
}
