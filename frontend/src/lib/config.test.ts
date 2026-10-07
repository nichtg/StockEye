import { describe, expect, it } from 'vitest';
import { resolveApiBaseUrl, resolveBasePath, routerBasename } from './config';

describe('config', () => {
  it('defaults the API to the same-origin /api', () => {
    expect(resolveApiBaseUrl(undefined)).toBe('/api');
    expect(resolveApiBaseUrl('')).toBe('/api');
  });

  it('accepts an absolute API URL and drops trailing slashes', () => {
    expect(resolveApiBaseUrl('https://203.0.113.7/api/')).toBe('https://203.0.113.7/api');
  });

  it('normalises the base path to a leading and trailing slash', () => {
    expect(resolveBasePath(undefined)).toBe('/');
    expect(resolveBasePath('/')).toBe('/');
    expect(resolveBasePath('StockEye')).toBe('/StockEye/');
    expect(resolveBasePath('/StockEye/')).toBe('/StockEye/');
  });

  it('derives the router basename from the base path', () => {
    expect(routerBasename('/')).toBe('/');
    expect(routerBasename('/StockEye/')).toBe('/StockEye');
  });

  it('accepts localhost over http but no other http host', () => {
    expect(resolveApiBaseUrl('http://localhost:8000/api')).toBe('http://localhost:8000/api');
    expect(resolveApiBaseUrl('http://127.0.0.1:8000/api')).toBe('http://127.0.0.1:8000/api');
    expect(() => resolveApiBaseUrl('http://example.com/api')).toThrow(/https/);
  });

  it.each([
    'api',
    'ftp://example.com/api',
    'https://user:pw@example.com/api',
    'https://example.com/api?x=1',
    'https://example.com/api#frag',
    '//example.com/api',
    '/api?x=1',
    'javascript:alert(1)',
  ])('rejects %s at build time', (bad) => {
    expect(() => resolveApiBaseUrl(bad)).toThrow(/VITE_API_BASE_URL/);
  });
});
