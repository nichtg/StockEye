export interface MockRequest {
  method: string;
  path: string;
  search: URLSearchParams;
  body: unknown;
}

export type MockHandler = (req: MockRequest) => { status?: number; body?: unknown } | undefined;

/** Stubs global fetch with a handler that sees every request; unknown routes answer 404. */
export function stubFetch(handler: MockHandler): MockRequest[] {
  const seen: MockRequest[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(
        input instanceof Request ? input.url : input.toString(),
        'http://localhost',
      );
      const raw = init?.body;
      const req: MockRequest = {
        method: init?.method ?? 'GET',
        path: url.pathname.replace(/^\/api/, ''),
        search: url.searchParams,
        body: typeof raw === 'string' ? (JSON.parse(raw) as unknown) : undefined,
      };
      seen.push(req);
      const result = handler(req);
      const status = result?.status ?? (result ? 200 : 404);
      const body =
        result?.body ?? (result ? undefined : { error: { code: 'not_found', message: 'nf' } });
      return Promise.resolve(
        new Response(body === undefined ? null : JSON.stringify(body), {
          status,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    }),
  );
  return seen;
}
