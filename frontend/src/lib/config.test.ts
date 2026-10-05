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
});
