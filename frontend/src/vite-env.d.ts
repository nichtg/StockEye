/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** API location: a path (`/api`, the default) or an absolute URL such as `https://api.example.com/api`. */
  readonly VITE_API_BASE_URL?: string;
  /** Path the app is served under, e.g. `/StockEye/` on GitHub Pages. Default `/`. */
  readonly VITE_BASE_PATH?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
