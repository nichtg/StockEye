import '@fontsource/ibm-plex-sans/latin-400.css';
import '@fontsource/ibm-plex-sans/latin-500.css';
import '@fontsource/ibm-plex-sans/latin-600.css';
import { QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router';
import { api } from './api/client';
import { App } from './App';
import { ROUTER_BASENAME } from './config';
import { startIfTopLevel } from './lib/frameGate';
import { NoticeProvider } from './components/NoticeProvider';
import { installSessionExpiry, queryClient } from './queryClient';
import { ColorModeProvider } from './theme/ColorModeProvider';

const root = document.getElementById('root');
if (!root) throw new Error('Missing #root element');

// A framed copy (clickjacking) stays hidden and neither calls the API nor renders.
startIfTopLevel(() => {
  installSessionExpiry(queryClient);
  // With a stored refresh token, get an access token before the first protected call. Failures
  // are handled by the request path (a 401 then signs the user out), so none are surfaced here.
  void api.initSession();

  createRoot(root).render(
    <StrictMode>
      <ColorModeProvider>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter basename={ROUTER_BASENAME}>
            <NoticeProvider>
              <App />
            </NoticeProvider>
          </BrowserRouter>
        </QueryClientProvider>
      </ColorModeProvider>
    </StrictMode>,
  );
});
