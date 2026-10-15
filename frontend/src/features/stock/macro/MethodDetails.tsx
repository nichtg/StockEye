import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import type { MacroReportOut, MacroStatsOut } from '../../../api/types';
import { DetailsAccordion } from '../../../components/DetailsAccordion';
import { Term } from '../../../components/Term';
import { formatMonthRange } from '../../../lib/format';
import { FindingList } from '../FindingList';
import { ScopeLabel } from '../ScopeLabel';
import { ScopeTable } from '../ScopeTable';
import { primaryStatsOf } from '../macroText';

/**
 * The period and the size of the evidence behind a set of findings, from the very stats the
 * findings were computed on. Each line is left out when its numbers are missing.
 */
function NewsBasis({ stats }: { stats: MacroStatsOut | null | undefined }) {
  if (!stats) return null;
  const period = formatMonthRange(stats.first_event, stats.last_event);
  const total = stats.n_used;
  const counts = {
    positive: stats.buckets.positive?.n ?? 0,
    neutral: stats.buckets.neutral?.n ?? 0,
    negative: stats.buckets.negative?.n ?? 0,
  };
  if (!period && total <= 0) return null;
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, mb: 1.5, maxWidth: 720 }}>
      {period && (
        <Typography variant="caption" component="p" sx={{ color: 'ink3' }}>
          Based on news from {period}. Each result compares the stock’s move on a news day and the
          next trading day with{' '}
          <Term id="market_adjusted_return" label="Market-adjusted move" suffix=".">
            what the market predicted
          </Term>
        </Typography>
      )}
      {total > 0 && (
        <Typography variant="caption" component="p" sx={{ color: 'ink3' }}>
          <Term id="news_days_studied" label="News days studied" suffix=":">
            {`${String(total)} news ${total === 1 ? 'day' : 'days'} studied`}
          </Term>{' '}
          <Term id="news_day_tones" label="Positive, neutral and negative news days">
            {`${String(counts.positive)} positive, ${String(counts.neutral)} neutral, ${String(counts.negative)} negative`}
          </Term>
        </Typography>
      )}
    </Box>
  );
}

/** The list "a, b and c". */
function joinClauses(parts: string[]): string {
  return parts.length > 1
    ? `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`
    : (parts[0] ?? '');
}

/**
 * Accounts for every news day found: studied (the primary scope's count), too little price history,
 * near earnings (when that scope drops them) and too recent (status ok but no 2-day result yet).
 */
function detailsLine(report: MacroReportOut): string {
  const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);
  const found = `${String(report.events_total)} news ${plural(report.events_total, 'day', 'days')} found`;
  const short = report.events_insufficient;
  const all = report.stats_all.n_used;
  const near =
    report.primary_scope === 'excluding_earnings'
      ? Math.max(0, all - report.stats_ex_earnings.n_used)
      : 0;
  const recent = Math.max(0, report.events_total - short - all);
  const clauses = [
    short > 0 &&
      `${String(short)} left out because there was too little price history around ${plural(short, 'it', 'them')}`,
    near > 0 && `${String(near)} near earnings ${plural(near, 'release', 'releases')}`,
    recent > 0 &&
      `${String(recent)} too recent to measure yet (the next trading day hasn’t closed)`,
  ].filter((c): c is string => c !== false);
  return clauses.length ? `${found}; ${joinClauses(clauses)}.` : `${found}.`;
}

/**
 * "How this was worked out": the method and the full evidence behind the headline answers. It is
 * demoted here, not removed. One block per scope: its label, period and day counts, findings with
 * their chance sentences and the numbers table; then the earnings note.
 */
export function MethodDetails({ report }: { report: MacroReportOut }) {
  const showScopes = report.secondary_scope != null;
  const primaryStats = primaryStatsOf(report);
  return (
    <DetailsAccordion title="How this was worked out" unmountOnExit>
      <Box sx={{ p: 2 }}>
        <Typography variant="subtitle1" sx={{ color: 'ink', mb: 0.5 }}>
          <ScopeLabel scope={report.primary_scope} />
        </Typography>
        <NewsBasis stats={primaryStats} />
        <Typography variant="caption" component="p" sx={{ color: 'ink3', mb: 1.5, maxWidth: 720 }}>
          {detailsLine(report)}
        </Typography>
        <FindingList findings={report.primary_findings} />
      </Box>
      <ScopeTable scope={report.primary_scope} stats={primaryStats} />
      {showScopes && (
        <>
          <Box sx={{ p: 2 }}>
            <Typography variant="subtitle1" sx={{ color: 'ink', mb: 0.5 }}>
              <ScopeLabel scope={report.secondary_scope} />
            </Typography>
            <NewsBasis stats={report.stats_all} />
            <FindingList findings={report.secondary_findings} />
          </Box>
          <ScopeTable scope="all_events" stats={report.stats_all} />
        </>
      )}
      {report.earnings_note && (
        <Typography variant="body2" sx={{ px: 2, pb: 2, color: 'ink2', maxWidth: 720 }}>
          <Term id="earnings" label="Earnings">
            {report.earnings_note}
          </Term>
        </Typography>
      )}
    </DetailsAccordion>
  );
}
