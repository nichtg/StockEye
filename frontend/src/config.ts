import { resolveApiBaseUrl, resolveBasePath, routerBasename } from './lib/config';

/** `VITE_API_BASE_URL`, default `/api` (same-origin: the dev proxy or the docker-compose nginx). */
export const API_BASE_URL = resolveApiBaseUrl(import.meta.env.VITE_API_BASE_URL);

/** `VITE_BASE_PATH`, default `/`. The router basename mirrors Vite's `base`. */
export const BASE_PATH = resolveBasePath(import.meta.env.VITE_BASE_PATH);
export const ROUTER_BASENAME = routerBasename(BASE_PATH);
