import '@fontsource/ibm-plex-sans/latin-400.css';
import '@fontsource/ibm-plex-sans/latin-500.css';
import '@fontsource/ibm-plex-sans/latin-600.css';
import { QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router';
import { api } from './api/client';
import { App } from './App';
import { installSessionExpiry, queryClient } from './queryClient';
import { ColorModeProvider } from './theme/ColorModeProvider';

installSessionExpiry(queryClient);
// Prime the CSRF cookie. If the API is down this fails quietly; unsafe requests retry it.
api.initCsrf().catch(() => undefined);

const root = document.getElementById('root');
if (!root) throw new Error('Missing #root element');

createRoot(root).render(
  <StrictMode>
    <ColorModeProvider>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </ColorModeProvider>
  </StrictMode>,
);
