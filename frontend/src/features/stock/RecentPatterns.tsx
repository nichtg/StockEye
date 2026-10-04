import Box from '@mui/material/Box';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import type { LatestPattern, PatternStatsOut, RecentPattern } from '../../api/types';
import { DetailsAccordion } from '../../components/DetailsAccordion';
import { Term } from '../../components/Term';
import type { Exchange } from '../../lib/exchange';
import { formatDate, formatPoints } from '../../lib/format';
import { isTermId, pct, patternSentence, wilsonInterval } from './technicalText';

type CountedPattern = RecentPattern & { stats: PatternStatsOut };

function hasStats(p: RecentPattern): p is CountedPattern {
  return p.stats != null && p.stats.n > 0;
}

const orDash = (fraction: number | null) => (fraction == null ? '–' : pct(fraction));

function StatsRow({ label, stats }: { label: string; stats: PatternStatsOut }) {
  const interval =
    stats.hit_rate == null ? null : wilsonInterval(Math.round(stats.hit_rate * stats.n), stats.n);
  return (
    <TableRow>
      <TableCell>{label}</TableCell>
      <TableCell align="right">{stats.n}</TableCell>
      <TableCell align="right">{orDash(stats.hit_rate)}</TableCell>
      <TableCell align="right">
        {interval ? `${pct(interval[0])} to ${pct(interval[1])}` : '–'}
      </TableCell>
      <TableCell align="right">{orDash(stats.base_rate)}</TableCell>
      <TableCell align="right">
        {stats.edge == null ? '–' : formatPoints(stats.edge * 100)}
      </TableCell>
    </TableRow>
  );
}

const indefinite = (label: string) => (/^[aeiou]/i.test(label) ? 'an' : 'a');

function LatestPatternSentence({
  latest,
  exchange,
}: {
  latest: LatestPattern;
  exchange: Exchange;
}) {
  const ago = latest.sessions_ago;
  return (
    <>
      {' '}
      The most recent was {indefinite(latest.label)}{' '}
      {isTermId(latest.pattern) ? <Term id={latest.pattern}>{latest.label}</Term> : latest.label} on{' '}
      {formatDate(latest.date, exchange)} ({ago} trading {ago === 1 ? 'day' : 'days'} ago), too old
      to count in this week’s outlook.
    </>
  );
}

/** Candlestick patterns from the last few sessions in plain words, with the numbers in Details. */
export function RecentPatterns({
  patterns,
  latest,
  exchange,
}: {
  patterns: RecentPattern[];
  /** The newest older pattern; only sent when `patterns` is empty. */
  latest?: LatestPattern | null;
  exchange: Exchange;
}) {
  if (patterns.length === 0) {
    return (
      <Typography>
        No patterns in the last 3 trading days.
        {latest && <LatestPatternSentence latest={latest} exchange={exchange} />}
      </Typography>
    );
  }
  const counted = patterns.filter(hasStats);
  return (
    <>
      <Box component="ul" sx={{ listStyle: 'none', m: 0, p: 0, display: 'grid', gap: 2 }}>
        {patterns.map((p) => (
          <li key={`${p.key}-${p.date}`}>
            <Typography sx={{ color: 'ink', fontWeight: 500 }}>
              {isTermId(p.key) ? <Term id={p.key}>{p.label}</Term> : p.label}
              <Box component="span" sx={{ color: 'ink3', fontWeight: 400, ml: 1 }}>
                {formatDate(p.date, exchange)}
              </Box>
            </Typography>
            <Typography variant="body2" sx={{ maxWidth: 640 }}>
              {patternSentence(p.stats, p.bias)}
            </Typography>
          </li>
        ))}
      </Box>
      {counted.length > 0 && (
        <Box sx={{ mt: 3 }}>
          <DetailsAccordion title="Show statistics">
            <TableContainer>
              <Table aria-label="Pattern statistics">
                <TableHead>
                  <TableRow>
                    <TableCell>Pattern</TableCell>
                    <TableCell align="right">Times seen</TableCell>
                    <TableCell align="right">
                      <Term id="pattern_reliability">Hit rate</Term>
                    </TableCell>
                    <TableCell align="right">
                      <Term id="statistical_reliability">95% range</Term>
                    </TableCell>
                    <TableCell align="right">
                      <Term id="base_rate">Typical week</Term>
                    </TableCell>
                    <TableCell align="right">
                      <Term id="base_rate">Edge</Term>
                    </TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {counted.map((p) => (
                    <StatsRow key={`${p.key}-${p.date}`} label={p.label} stats={p.stats} />
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </DetailsAccordion>
        </Box>
      )}
    </>
  );
}
