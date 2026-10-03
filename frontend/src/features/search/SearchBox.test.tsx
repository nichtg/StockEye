import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes, useLocation } from 'react-router';
import { stubFetch } from '../../test/mockApi';
import { renderApp } from '../../test/render';
import { SearchBox } from './SearchBox';

function Where() {
  return <div data-testid="where">{useLocation().pathname}</div>;
}

function setup() {
  return renderApp(
    <>
      <SearchBox />
      <Routes>
        <Route path="*" element={<Where />} />
      </Routes>
    </>,
  );
}

const matches = [
  { symbol: 'D05.SI', name: 'DBS Group Holdings Ltd', exchange: 'SGX' },
  { symbol: 'DBSDF', name: 'DBS Group (OTC)', exchange: 'US' },
];

describe('SearchBox', () => {
  it('searches after a pause, lists symbol, name and exchange, and Enter opens the stock', async () => {
    const seen = stubFetch((req) => {
      if (req.path === '/stocks/search') return { body: matches };
      return undefined;
    });
    const user = userEvent.setup();
    setup();

    await user.type(screen.getByRole('combobox', { name: 'Search for a stock' }), 'dbs');
    const first = await screen.findByRole('option', { name: /D05\.SI/ });
    expect(first).toHaveTextContent('DBS Group Holdings Ltd');
    expect(first).toHaveTextContent('SGX');
    // Debounced: typing three characters produced one request, for the full text.
    const searches = seen.filter((r) => r.path === '/stocks/search');
    expect(searches).toHaveLength(1);
    expect(searches[0]?.search.get('q')).toBe('dbs');

    await user.keyboard('{Enter}');
    await waitFor(() => {
      expect(screen.getByTestId('where')).toHaveTextContent('/stock/D05.SI');
    });
  });

  it('focuses with Ctrl+K', async () => {
    stubFetch(() => undefined);
    const user = userEvent.setup();
    setup();
    await user.keyboard('{Control>}k{/Control}');
    expect(screen.getByRole('combobox', { name: 'Search for a stock' })).toHaveFocus();
  });

  it('says so when nothing matches', async () => {
    stubFetch((req) => (req.path === '/stocks/search' ? { body: [] } : undefined));
    const user = userEvent.setup();
    setup();
    await user.type(screen.getByRole('combobox', { name: 'Search for a stock' }), 'zzzz');
    expect(await screen.findByText(/No US or SGX stocks match “zzzz”/)).toBeInTheDocument();
  });

  it('shows an inline error when the search fails', async () => {
    stubFetch((req) =>
      req.path === '/stocks/search'
        ? { status: 500, body: { error: { code: 'x', message: 'boom', request_id: '' } } }
        : undefined,
    );
    const user = userEvent.setup();
    setup();
    await user.type(screen.getByRole('combobox', { name: 'Search for a stock' }), 'dbs');
    expect(await screen.findByRole('alert')).toHaveTextContent(/something went wrong on our side/i);
  });
});
