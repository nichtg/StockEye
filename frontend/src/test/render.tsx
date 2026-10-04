import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router';
import { NoticeProvider } from '../components/NoticeProvider';
import { ColorModeProvider } from '../theme/ColorModeProvider';

export function renderApp(ui: ReactElement, { route = '/' }: { route?: string } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return {
    client,
    ...render(
      <ColorModeProvider>
        <QueryClientProvider client={client}>
          <NoticeProvider>
            <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
          </NoticeProvider>
        </QueryClientProvider>
      </ColorModeProvider>,
    ),
  };
}

/** jsdom has no matchMedia; this stub reports the given system colour scheme. */
export function stubSystemColorScheme(scheme: 'light' | 'dark'): void {
  vi.stubGlobal(
    'matchMedia',
    (query: string): MediaQueryList =>
      ({
        matches: query.includes('dark') ? scheme === 'dark' : false,
        media: query,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        addListener: () => undefined,
        removeListener: () => undefined,
        dispatchEvent: () => false,
        onchange: null,
      }) as MediaQueryList,
  );
}
