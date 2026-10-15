import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useLocation } from 'react-router';
import type { OverviewRow } from '../../api/types';
import { renderApp } from '../../test/render';
import { TableControls } from './TableControls';
import { useTableState } from './useTableState';

function row(symbol: string, country: string | null): OverviewRow {
  return {
    symbol,
    name: `${symbol} Corp`,
    exchange: 'US',
    currency: 'USD',
    last_price: 10,
    change_1w_pct: 1,
    sparkline: [1, 2, 3],
    lean: 'neutral',
    country,
    sector: null,
    market_cap: 1e9,
    status: 'ok',
    status_reason: null,
  };
}

const COUNTRIES = ['Brazil', 'Canada', 'France', 'Japan', 'Mexico', 'Singapore'];
// Singapore twice, so the counts differ.
const MANY = [...COUNTRIES, 'Singapore'].map((c, i) => row(`S${i}`, c));

function Harness({ rows, namespace = '' }: { rows: OverviewRow[]; namespace?: string }) {
  const state = useTableState({ namespace, columns: 'discover' });
  return (
    <>
      <output data-testid="loc">{useLocation().search}</output>
      <TableControls rows={rows} state={state} />
    </>
  );
}

describe('TableControls country filter', () => {
  it('uses buttons for 3 countries and a select for 6', () => {
    const { unmount } = renderApp(
      <Harness rows={['Brazil', 'Canada', 'France'].map((c, i) => row(`S${i}`, c))} />,
    );
    expect(screen.getByRole('radiogroup', { name: 'Filter by country' })).toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    unmount();

    renderApp(<Harness rows={MANY} />);
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: /Country/ })).toBeInTheDocument();
  });

  it('keeps 5 countries as buttons', () => {
    renderApp(<Harness rows={COUNTRIES.slice(0, 5).map((c, i) => row(`S${i}`, c))} />);
    expect(screen.getAllByRole('radio')).toHaveLength(6);
  });

  it('writes the chosen country to the URL in the select, for both namespaces', async () => {
    const user = userEvent.setup();
    const { unmount } = renderApp(<Harness rows={MANY} />);
    await user.click(screen.getByRole('combobox', { name: /Country/ }));
    await user.click(screen.getByRole('option', { name: /Canada/ }));
    expect(screen.getByTestId('loc')).toHaveTextContent('?country=Canada');
    unmount();

    renderApp(<Harness rows={MANY} namespace="discover" />);
    await user.click(screen.getByRole('combobox', { name: /Country/ }));
    await user.click(screen.getByRole('option', { name: /Singapore/ }));
    expect(screen.getByTestId('loc')).toHaveTextContent('?discoverCountry=Singapore');
  });

  it('shows counts, a check on the selected item and a divider after All countries', async () => {
    const user = userEvent.setup();
    renderApp(<Harness rows={MANY} />, { route: '/?country=Singapore' });
    await user.click(screen.getByRole('combobox', { name: /Country/ }));
    const listbox = screen.getByRole('listbox');
    const options = within(listbox).getAllByRole('option');
    expect(options[0]).toHaveTextContent('All countries');
    expect(listbox.querySelector('hr')).not.toBeNull();
    const singapore = within(listbox).getByRole('option', { name: /Singapore/ });
    expect(singapore).toHaveTextContent('2');
    expect(singapore).toHaveAttribute('aria-selected', 'true');
    // Every option reserves the check's space; only the selected one shows it.
    const visibleChecks = options.filter((o) => {
      const icon = o.querySelector('svg');
      return icon !== null && getComputedStyle(icon).visibility !== 'hidden';
    });
    expect(visibleChecks).toEqual([singapore]);
  });

  it('keeps an unknown country from the URL selected, with a count of 0', async () => {
    const user = userEvent.setup();
    renderApp(<Harness rows={MANY} />, { route: '/?country=Peru' });
    await user.click(screen.getByRole('combobox', { name: /Country/ }));
    const peru = screen.getByRole('option', { name: /Peru/ });
    expect(peru).toHaveAttribute('aria-selected', 'true');
    expect(peru).toHaveTextContent('0');
  });

  it('opens with Enter and closes with Escape', async () => {
    const user = userEvent.setup();
    renderApp(<Harness rows={MANY} />);
    screen.getByRole('combobox', { name: /Country/ }).focus();
    await user.keyboard('{Enter}');
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });
});
