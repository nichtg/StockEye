import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import type { MacroStatsOut } from '../../../api/types';
import { Term } from '../../../components/Term';
import { visuallyHidden } from '../../../lib/a11y';
import { formatPct } from '../../../lib/format';
import { symmetricAxis } from './chartScale';

type BucketKey = 'positive' | 'neutral' | 'negative';
type Bucket = MacroStatsOut['buckets'][string];

const ROWS: { key: BucketKey; name: string }[] = [
  { key: 'positive', name: 'Positive news' },
  { key: 'neutral', name: 'Neutral news' },
  { key: 'negative', name: 'Negative news' },
];

/** Drawing units: the plot stretches to its column; strokes stay crisp via non-scaling-stroke. */
const W = 1000;
const ROW_H = 40;
const BAR_H = 16;
const CAP = 5;
const FADE = 0.4;

interface Tested {
  kind: 'tested';
  mean: number; // percent
  low: number;
  high: number;
  faded: boolean;
}

interface Row {
  key: BucketKey;
  name: string;
  n: number;
  result: Tested | { kind: 'untested' };
}

const days = (n: number) => `${String(n)} ${n === 1 ? 'day' : 'days'}`;
const pct = (v: number) => formatPct(v, { signed: true });

function rowOf(key: BucketKey, name: string, b: Bucket | undefined): Row {
  const n = b?.n ?? 0;
  if (b?.mean_car_0_1 == null || b.ci_low_0_1 == null || b.ci_high_0_1 == null) {
    return { key, name, n, result: { kind: 'untested' } };
  }
  return {
    key,
    name,
    n,
    result: {
      kind: 'tested',
      mean: b.mean_car_0_1 * 100,
      low: b.ci_low_0_1 * 100,
      high: b.ci_high_0_1 * 100,
      // The label is the rounded one the findings use, so the fade matches what the text says.
      faded: b.label === 'no_clear_effect',
    },
  };
}

const untestedText = (r: Row, minN: number) =>
  `Not enough data (${days(r.n)}; ${String(minN)} needed)`;

function ariaSummary(rows: Row[], minN: number): string {
  const parts = rows.map((r) =>
    r.result.kind === 'tested'
      ? `${r.name} ${pct(r.result.mean)} (${days(r.n)})${r.result.faded ? ', could be chance' : ''}`
      : `${r.name}: ${untestedText(r, minN)}`,
  );
  return `Average market-adjusted 2-day move by type of news day. ${parts.join('; ')}.`;
}

function directionColor(mean: number): string {
  return mean > 0 ? 'var(--se-up)' : mean < 0 ? 'var(--se-down)' : 'var(--se-ink3)';
}

const GRID = {
  display: 'grid',
  gridTemplateColumns: 'minmax(88px, 140px) minmax(0, 1fr) 76px',
  columnGap: 1.5,
} as const;

/**
 * Average market-adjusted 2-day move for positive, neutral and negative news days: a bar from zero
 * with a 95% range whisker. Direction is colour plus a glyph and signed value. A bar whose result
 * could be chance is faded; a bucket with too few days draws no bar and says so.
 */
export function BucketChart({ stats }: { stats: MacroStatsOut }) {
  const rows = ROWS.map(({ key, name }) => rowOf(key, name, stats.buckets[key]));
  const tested = rows.flatMap((r) => (r.result.kind === 'tested' ? [r.result] : []));
  const axis = tested.length
    ? symmetricAxis(
        Math.max(...tested.flatMap((t) => [Math.abs(t.low), Math.abs(t.high), Math.abs(t.mean)])),
      )
    : null;
  const frac = (v: number) => (axis ? (v + axis.max) / (2 * axis.max) : 0.5);
  const x = (v: number) => frac(v) * W;
  const mid = ROW_H / 2;

  return (
    <Box>
      <Typography variant="body2" sx={{ color: 'ink2', mb: 1.5 }}>
        <Term id="market_adjusted_return" label="Market-adjusted move">
          Average market-adjusted 2-day move
        </Term>{' '}
        by type of news day
      </Typography>
      <Box role="img" aria-label={ariaSummary(rows, stats.min_n)}>
        {rows.map((r) => {
          const t = r.result.kind === 'tested' ? r.result : null;
          return (
            <Box
              key={r.key}
              data-testid={`bucket-row-${r.key}`}
              sx={{ ...GRID, alignItems: 'center', minHeight: ROW_H }}
            >
              <Box>
                <Typography variant="body2" sx={{ color: 'ink', lineHeight: 1.3 }}>
                  {r.name}
                </Typography>
                {t && (
                  <Typography variant="caption" sx={{ color: 'ink3' }}>
                    {days(r.n)}
                  </Typography>
                )}
              </Box>
              {t && axis ? (
                <>
                  <svg
                    viewBox={`0 0 ${String(W)} ${String(ROW_H)}`}
                    preserveAspectRatio="none"
                    width="100%"
                    height={ROW_H}
                    aria-hidden="true"
                    style={{ display: 'block' }}
                  >
                    {axis.ticks.map((v) => (
                      <line
                        key={v}
                        x1={x(v)}
                        x2={x(v)}
                        y1={0}
                        y2={ROW_H}
                        stroke={v === 0 ? 'var(--se-ink3)' : 'var(--se-line)'}
                        strokeWidth={1}
                        vectorEffect="non-scaling-stroke"
                      />
                    ))}
                    <g data-testid={`bucket-bar-${r.key}`} opacity={t.faded ? FADE : 1}>
                      <rect
                        x={Math.min(x(0), x(t.mean))}
                        y={(ROW_H - BAR_H) / 2}
                        width={Math.max(1, Math.abs(x(t.mean) - x(0)))}
                        height={BAR_H}
                        fill={directionColor(t.mean)}
                      />
                      <g
                        data-testid={`bucket-whisker-${r.key}`}
                        stroke="var(--se-ink)"
                        strokeWidth={1.5}
                      >
                        <line
                          x1={x(t.low)}
                          x2={x(t.high)}
                          y1={mid}
                          y2={mid}
                          vectorEffect="non-scaling-stroke"
                        />
                        <line
                          x1={x(t.low)}
                          x2={x(t.low)}
                          y1={mid - CAP}
                          y2={mid + CAP}
                          vectorEffect="non-scaling-stroke"
                        />
                        <line
                          x1={x(t.high)}
                          x2={x(t.high)}
                          y1={mid - CAP}
                          y2={mid + CAP}
                          vectorEffect="non-scaling-stroke"
                        />
                      </g>
                    </g>
                  </svg>
                  <Typography
                    variant="body2"
                    sx={{ fontWeight: 600, textAlign: 'right', color: directionColor(t.mean) }}
                  >
                    <span aria-hidden="true">{t.mean > 0 ? '▲ ' : t.mean < 0 ? '▼ ' : ''}</span>
                    {pct(t.mean)}
                  </Typography>
                </>
              ) : (
                <Typography variant="caption" sx={{ color: 'ink3', gridColumn: '2 / span 2' }}>
                  {untestedText(r, stats.min_n)}
                </Typography>
              )}
            </Box>
          );
        })}
        {axis && (
          <Box sx={{ ...GRID, mt: 0.5 }} aria-hidden="true">
            <span />
            <Box sx={{ position: 'relative', height: 18 }}>
              {axis.ticks.map((v, i) => (
                <Typography
                  key={v}
                  variant="caption"
                  sx={{
                    position: 'absolute',
                    left: `${String(frac(v) * 100)}%`,
                    // The end labels stay inside the column so nothing overflows at 375px.
                    transform:
                      i === 0
                        ? 'none'
                        : i === axis.ticks.length - 1
                          ? 'translateX(-100%)'
                          : 'translateX(-50%)',
                    color: 'ink3',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {v === 0 ? '0%' : pct(v)}
                </Typography>
              ))}
            </Box>
            <span />
          </Box>
        )}
      </Box>
      <Typography variant="caption" sx={{ display: 'block', color: 'ink3', mt: 1 }}>
        Faded: could be chance. Lines show the likely range.
      </Typography>
      <Box sx={visuallyHidden}>
        <table>
          <caption>Average market-adjusted 2-day move by type of news day</caption>
          <thead>
            <tr>
              <th>News</th>
              <th>Days</th>
              <th>Average move</th>
              <th>Likely range</th>
              <th>Could be chance</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key}>
                <td>{r.name}</td>
                <td>{r.n}</td>
                {r.result.kind === 'tested' ? (
                  <>
                    <td>{pct(r.result.mean)}</td>
                    <td>{`${pct(r.result.low)} to ${pct(r.result.high)}`}</td>
                    <td>{r.result.faded ? 'Yes' : 'No'}</td>
                  </>
                ) : (
                  <td colSpan={3}>{untestedText(r, stats.min_n)}</td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </Box>
    </Box>
  );
}
