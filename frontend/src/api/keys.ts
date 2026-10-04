export const meKey = ['me'] as const;
/** Set when the user signed out on purpose (account deleted), so the guard adds no ?next=; the login page clears it. */
export const signedOutOnPurposeKey = ['session', 'signed-out-on-purpose'] as const;
export const adminUsersKey = ['admin', 'users'] as const;
export const adminUsersPageKey = (query: string, page: number) =>
  [...adminUsersKey, { query, page }] as const;
export const adminProvidersKey = ['admin', 'providers'] as const;
export const watchlistRootKey = ['watchlist'] as const;
export const overviewKey = ['watchlist', 'overview'] as const;
export const stockKey = (symbol: string) => ['stock', symbol] as const;
export const chartKey = (symbol: string, range: string) =>
  ['stock', symbol, 'chart', range] as const;
export const chartRootKey = (symbol: string) => ['stock', symbol, 'chart'] as const;
export const newsKey = (symbol: string) => ['stock', symbol, 'news'] as const;
export const technicalKey = (symbol: string) => ['stock', symbol, 'technical'] as const;
export const macroKey = (symbol: string) => ['stock', symbol, 'macro'] as const;
export const searchKey = (q: string) => ['search', q] as const;
export const watchlistKey = ['watchlist', 'symbols'] as const;
