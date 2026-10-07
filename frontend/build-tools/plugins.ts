import { copyFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Plugin } from 'vite';

/** The origin a `connect-src` needs for this API URL: `'self'` when it is a same-origin path. */
export function connectSrcFor(apiBaseUrl: string): string {
  try {
    const url = new URL(apiBaseUrl);
    if (url.protocol === 'http:' || url.protocol === 'https:') return url.origin;
  } catch {
    // Not absolute: a path on the page's own origin.
  }
  return "'self'";
}

export function buildCsp(apiBaseUrl: string): string {
  return [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    `connect-src ${connectSrcFor(apiBaseUrl)}`,
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
  ].join('; ');
}

/**
 * Injects the meta Content-Security-Policy into the built index.html only. The dev server needs
 * inline scripts and a websocket for hot reload, which this policy would block.
 */
export function cspPlugin(apiBaseUrl: string): Plugin {
  return {
    name: 'stockeye-csp',
    apply: 'build',
    transformIndexHtml: () => [
      {
        tag: 'meta',
        attrs: { 'http-equiv': 'Content-Security-Policy', content: buildCsp(apiBaseUrl) },
        injectTo: 'head-prepend',
      },
    ],
  };
}

/** GitHub Pages serves 404.html for unknown paths; a copy of the SPA shell makes deep links work. */
export function spa404Plugin(): Plugin {
  let outDir = 'dist';
  return {
    name: 'stockeye-spa-404',
    apply: 'build',
    configResolved(config) {
      outDir = resolve(config.root, config.build.outDir);
    },
    closeBundle() {
      // After a failed build there is no index.html; do not mask the real error with ours.
      const index = resolve(outDir, 'index.html');
      if (existsSync(index)) copyFileSync(index, resolve(outDir, '404.html'));
    },
  };
}
