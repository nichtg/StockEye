import type { components } from './schema';

type S = components['schemas'];

export type Role = 'user' | 'admin';
export type UserStatus = 'active' | 'disabled';
export type User = S['UserOut'];
export type Session = S['SessionOut'];
export type AdminUser = S['AdminUserOut'];
export type AdminUserPage = S['AdminUserPage'];
export type AdminUserPatch = S['UserPatch'];
/** The schema types these as required, but unlimited providers (e.g. Yahoo) legitimately omit them. */
export type ProviderStatus = Omit<S['ProviderStatus'], 'daily_limit' | 'resets_at'> & {
  daily_limit: number | null;
  resets_at: string | null;
};
export type ProviderLevel = ProviderStatus['level'];

export type DataStatus = S['DataStatus'];
export type DataState = DataStatus['state'];
export type StockOut = S['StockOut'];
export type SymbolMatch = S['SymbolMatch'];
export type OverviewRow = S['OverviewRow'];
export type WatchlistOut = S['WatchlistOut'];
export type ChartData = S['ChartData'];
export type Candle = S['Candle'];
export type SeriesPoint = S['SeriesPoint'];
export type ChartMarker = S['Marker'];
export type RangeKey = ChartData['range'];
export type TechnicalReport = S['TechnicalReport'];
export type SignalOut = S['SignalOut'];
export type RecentPattern = S['RecentPattern'];
export type PatternStatsOut = S['PatternStatsOut'];
export type MacroResponse = S['MacroResponse'];
export type Ingestion = S['IngestionOut'];
export type NewsProgress = S['NewsProgressOut'];
export type MacroReportOut = S['MacroReportOut'];
export type FindingOut = S['FindingOut'];
export type TopEventOut = S['TopEventOut'];
export type MacroStatsOut = S['MacroStatsOut'];
export type Lean = S['OutlookOut']['lean'];
export type Reliability = NonNullable<S['FindingOut']['reliability']>;

/** One entry of `error.details` on a 422 response. `field` is a dotted path such as "password". */
export interface FieldIssue {
  field: string;
  message: string;
}

export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    request_id: string;
    details: FieldIssue[] | null;
  };
}
