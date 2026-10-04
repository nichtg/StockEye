import Box from '@mui/material/Box';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import type { MacroStatsOut, Reliability } from '../../api/types';
import { Term } from '../../components/Term';
import { formatPct, formatSigned } from '../../lib/format';
import { RELIABILITY_LABEL, SCOPE_NAME, pValueText, type Scope } from './macroText';
import { ScopeLabel } from './ScopeLabel';

interface Row {
  measure: string;
  events: number;
  result: string;
  p: number | null;
  label: Reliability | null;
}

const move = (fraction: number | null) =>
  fraction == null ? '–' : formatPct(fraction * 100, { signed: true });

function rowsOf(stats: MacroStatsOut): Row[] {
  const rows: Row[] = [];
  for (const key of ['positive', 'negative'] as const) {
    const b = stats.buckets[key];
    if (!b) continue;
    rows.push({
      measure: key === 'positive' ? 'Positive-news days' : 'Negative-news days',
      events: b.n,
      result: move(b.mean_car_0_1),
      p: b.p_value,
      label: b.label,
    });
  }
  const d = stats.difference;
  if (d) {
    rows.push({
      measure: 'Positive minus negative',
      events: d.n_pos + d.n_neg,
      result: move(d.mean_diff),
      p: d.p_value,
      label: d.label,
    });
  }
  const c = stats.correlation;
  if (c) {
    rows.push({
      measure: 'Sentiment versus move',
      events: c.n,
      result: `correlation ${formatSigned(c.rho, 2)}`,
      p: c.p_value,
      label: c.label,
    });
  }
  return rows;
}

/** The raw numbers behind a set of findings: one row per measure. Lives inside Details. */
export function ScopeTable({ scope, stats }: { scope: Scope; stats: MacroStatsOut }) {
  return (
    <Box sx={{ mb: 3 }}>
      <Typography variant="subtitle1" sx={{ color: 'ink', px: 2, pt: 1.5 }}>
        <ScopeLabel scope={scope} />
      </Typography>
      <TableContainer>
        <Table aria-label={SCOPE_NAME[scope]}>
          <TableHead>
            <TableRow>
              <TableCell>Measure</TableCell>
              <TableCell align="right">News days</TableCell>
              <TableCell align="right">
                <Term id="market_adjusted_return">Market-adjusted move</Term>
              </TableCell>
              <TableCell align="right">
                <Term id="p_value">p-value</Term>
              </TableCell>
              <TableCell>
                <Term id="news_effect">News effect</Term>
              </TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rowsOf(stats).map((r) => (
              <TableRow key={r.measure}>
                <TableCell>{r.measure}</TableCell>
                <TableCell align="right">{r.events}</TableCell>
                <TableCell align="right">{r.result}</TableCell>
                <TableCell align="right">{pValueText(r.p)}</TableCell>
                <TableCell>{r.label ? RELIABILITY_LABEL[r.label] : 'Too few news days'}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}
