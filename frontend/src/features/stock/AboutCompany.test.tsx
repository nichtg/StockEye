import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { Profile } from '../../api/types';
import { profileFixture } from '../../test/fixtures';
import { stubFetch } from '../../test/mockApi';
import { renderApp } from '../../test/render';
import { AboutCompany } from './AboutCompany';

function show(profile: Partial<Profile>) {
  stubFetch((req) =>
    req.path === '/stocks/AAPL/profile' ? { body: { ...profileFixture, ...profile } } : undefined,
  );
  return renderApp(<AboutCompany symbol="AAPL" name="Apple Inc." exchange="US" currency="USD" />);
}

const ALL_NULL: Partial<Profile> = {
  description: null,
  sector: null,
  industry: null,
  country: null,
  website: null,
  employees: null,
  market_cap: null,
  pe_ratio: null,
  dividend_yield: null,
  week52_low: null,
  week52_high: null,
  avg_volume: null,
};

describe('AboutCompany', () => {
  it('shows the description and the formatted key facts with glossary terms', async () => {
    show({});
    expect(await screen.findByRole('heading', { name: 'About Apple Inc.' })).toBeInTheDocument();
    expect(screen.getByText(/Apple designs, makes and sells/)).toBeInTheDocument();
    expect(screen.getByText('$3.2T')).toBeInTheDocument();
    expect(screen.getByText('31.5')).toBeInTheDocument();
    expect(screen.getByText('0.44%')).toBeInTheDocument();
    expect(screen.getByText('$164.08 – $237.23')).toBeInTheDocument();
    expect(screen.getByText('55.3M')).toBeInTheDocument();
    expect(screen.getByText('164,000')).toBeInTheDocument();
    for (const term of ['Market cap', 'P/E ratio', 'Dividend yield', '52-week range']) {
      expect(screen.getByRole('button', { name: `What is ${term}?` })).toBeInTheDocument();
    }
    const site = screen.getByRole('link', { name: 'apple.com' });
    expect(site).toHaveAttribute('href', 'https://www.apple.com/');
    expect(site).toHaveAttribute('target', '_blank');
    expect(site).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('hides each fact that is null', async () => {
    show({ market_cap: null, dividend_yield: null, employees: null, week52_low: null });
    await screen.findByText('31.5');
    expect(screen.queryByText('Market cap')).not.toBeInTheDocument();
    expect(screen.queryByText('Dividend yield')).not.toBeInTheDocument();
    expect(screen.queryByText('Employees')).not.toBeInTheDocument();
    expect(screen.queryByText('52-week range')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'What is P/E ratio?' })).toBeInTheDocument();
  });

  it.each(['javascript:alert(1)', 'data:text/html,hi', 'not a url'])(
    'does not render %s as a website link',
    async (website) => {
      show({ website });
      await screen.findByText('31.5');
      expect(screen.queryByRole('link')).not.toBeInTheDocument();
      expect(screen.queryByText('Website')).not.toBeInTheDocument();
    },
  );

  it('renders nothing at all when every field is null', async () => {
    const seen = stubFetch((req) =>
      req.path === '/stocks/AAPL/profile'
        ? { body: { ...profileFixture, ...ALL_NULL } }
        : undefined,
    );
    const { container } = renderApp(
      <AboutCompany symbol="AAPL" name="Apple Inc." exchange="US" currency="USD" />,
    );
    await vi.waitFor(() => {
      expect(seen.length).toBeGreaterThan(0);
      expect(container).toBeEmptyDOMElement();
    });
  });

  it('shows a quiet line when the data is not fully fresh', async () => {
    show({ data_status: { state: 'stale', reason: 'Company details are 2 days old.' } });
    expect(await screen.findByText('Company details are 2 days old.')).toBeInTheDocument();
  });

  describe('description clamp', () => {
    const LONG = 'A long description. '.repeat(60);

    afterEach(() => {
      // Restore jsdom's zero-sized layout.
      delete (HTMLElement.prototype as { scrollHeight?: number }).scrollHeight;
      delete (HTMLElement.prototype as { clientHeight?: number }).clientHeight;
    });

    it('offers Show more only when the text overflows, and toggles aria-expanded', async () => {
      Object.defineProperty(HTMLElement.prototype, 'scrollHeight', {
        configurable: true,
        get: () => 200,
      });
      Object.defineProperty(HTMLElement.prototype, 'clientHeight', {
        configurable: true,
        get: () => 80,
      });
      const user = userEvent.setup();
      show({ description: LONG });
      const button = await screen.findByRole('button', { name: 'Show more' });
      expect(button).toHaveAttribute('aria-expanded', 'false');
      await user.click(button);
      const less = screen.getByRole('button', { name: 'Show less' });
      expect(less).toHaveAttribute('aria-expanded', 'true');
      await user.click(less);
      expect(screen.getByRole('button', { name: 'Show more' })).toHaveAttribute(
        'aria-expanded',
        'false',
      );
    });

    it('has no toggle when the text fits', async () => {
      show({ description: 'Short.' });
      await screen.findByText('Short.');
      expect(screen.queryByRole('button', { name: /Show (more|less)/ })).not.toBeInTheDocument();
    });
  });
});
