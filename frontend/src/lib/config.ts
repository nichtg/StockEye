// Pure helpers for the two build-time settings. Kept free of `import.meta` so vite.config.ts can
// share them with the app.

/**
 * Where the API lives: a same-origin path such as `/api`, or an absolute https URL without
 * credentials, query or fragment (http only for localhost). No trailing slash. Anything else
 * throws, which fails the build instead of shipping a policy that trusts a surprising origin.
 */
export function resolveApiBaseUrl(raw: string | undefined): string {
  const value = (raw ?? '').trim();
  if (!value) return '/api';
  if (value.startsWith('/')) {
    if (value.startsWith('//') || /[?#\\\s]/.test(value)) {
      throw new Error(`VITE_API_BASE_URL must be a plain path or an absolute URL, got "${value}"`);
    }
  } else {
    let url: URL;
    try {
      url = new URL(value);
    } catch {
      throw new Error(
        `VITE_API_BASE_URL must start with "/" or be an absolute URL, got "${value}"`,
      );
    }
    const local = url.hostname === 'localhost' || url.hostname === '127.0.0.1';
    if (url.protocol !== 'https:' && !(url.protocol === 'http:' && local)) {
      throw new Error('VITE_API_BASE_URL must use https (http only for localhost or 127.0.0.1)');
    }
    if (url.username || url.password || url.search || url.hash || /[?#]/.test(value)) {
      throw new Error('VITE_API_BASE_URL must not contain credentials, a query or a fragment');
    }
  }
  return value.replace(/\/+$/, '') || '/';
}

/** Vite `base`: always a leading and a trailing slash, `/` by default. */
export function resolveBasePath(raw: string | undefined): string {
  const value = (raw ?? '').trim();
  if (!value || value === '/') return '/';
  return `/${value.replace(/^\/+|\/+$/g, '')}/`;
}

/** React Router basename for a base path: `/StockEye/` becomes `/StockEye`, `/` becomes `/`. */
export function routerBasename(basePath: string): string {
  return basePath === '/' ? '/' : basePath.replace(/\/+$/, '');
}
