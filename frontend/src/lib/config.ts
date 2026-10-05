// Pure helpers for the two build-time settings. Kept free of `import.meta` so vite.config.ts can
// share them with the app.

/** Where the API lives: a same-origin path such as `/api`, or an absolute URL. No trailing slash. */
export function resolveApiBaseUrl(raw: string | undefined): string {
  const value = (raw ?? '').trim();
  if (!value) return '/api';
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
