import { describe, expect, it } from 'vitest';
import { buildCsp, connectSrcFor } from './plugins';

describe('CSP plugin output', () => {
  it('uses the API origin for an absolute API URL', () => {
    expect(buildCsp('https://203.0.113.7/api')).toBe(
      "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; " +
        "font-src 'self'; connect-src https://203.0.113.7; base-uri 'self'; form-action 'self'; " +
        "object-src 'none'",
    );
  });

  it("uses 'self' for a relative API URL", () => {
    expect(buildCsp('/api')).toContain("connect-src 'self';");
    expect(connectSrcFor('/api')).toBe("'self'");
  });

  it('keeps a non-default port in the origin and drops the path', () => {
    expect(connectSrcFor('http://localhost:8000/api')).toBe('http://localhost:8000');
  });

  it('never allows inline scripts', () => {
    expect(buildCsp('/api')).not.toMatch(/script-src[^;]*unsafe/);
  });
});
