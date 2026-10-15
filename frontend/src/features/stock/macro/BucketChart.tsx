import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import type { MacroStatsOut } from '../../../api/types';
import { Direction } from '../../../components/Direction';
import { Term } from '../../../components/Term';
import { visuallyHidden } from '../../../lib/a11y';
import { directionOf, formatPct } from '../../../lib/format';
import { isTested, symmetricAxis, type Axis } from './chartScale';

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
const VALUE_COL = 72;

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
const pct = (v: number, digits = 1) => formatPct(v, { signed: true, digits });

function rowOf(key: BucketKey, name: string, b: Bucket | undefined): Row {
  const n = b?.n ?? 0;
  if (!b || !isTested(b)) return { key, name, n, result: { kind: 'untested' } };
  return {
    key,
    name,
    n,
    result: {
      kind: 'tested',
      mean: (b.mean_car_0_1 ?? 0) * 100,
      low: (b.ci_low_0_1 ?? 0) * 100,
      high: (b.ci_high_0_1 ?? 0) * 100,
      // The label is the rounded one the findings use, so the fade matches what the text says.
      faded: b.label === 'no_clear_effect',
    },
  };
}

/** Too few days to test, or enough days but no usable reading. */
const untestedText = (r: Row, minN: number) =>
  r.n >= minN
    ? `No usable reading yet (${days(r.n)})`
    : `Not enough data (${days(r.n)}; ${String(minN)} needed)`;

function ariaSummary(rows: Row[], minN: number): string {
  const parts = rows.map((r) =>
    r.result.kind === 'tested'
      ? `${r.name} ${pct(r.result.mean)} (${days(r.n)})${r.result.faded ? ', could be chance' : ''}`
      : `${r.name}: ${untestedText(r, minN)}`,
  );
  return `Average market-adjusted 2-day move by type of news day. ${parts.join('; ')}.`;
}

const BAR_COLOR = { up: 'var(--se-up)', down: 'var(--se-down)', flat: 'var(--se-ink3)' } as const;

const GRID = {
  display: 'grid',
  gridTemplateColumns: `minmax(72px, max-content) minmax(0, 1fr) ${String(VALUE_COL)}px`,
  columnGap: 1.5,
} as const;

/** Zero line and gridlines, drawn in every row (also the untested ones) so they read as one axis. */
function Grid({ axis, x }: { axis: Axis; x: (v: number) => number }) {
  return (
    <>
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
    </>
  );
}

/**
 * Average market-adjusted 2-day move for positive, neutral and negative news days: a bar from zero
 * with a 95% range whisker. Direction is colour plus a glyph and signed value. A bar whose result
 * could be chance is faded; a bucket with too few days draws no bar and says so. Render it only
 * when at least one bucket is tested (the caller checks); otherwise there is no axis to draw.
 */
export function BucketChart({ stats }: { stats: MacroStatsOut }) {
  const rows = ROWS.map(({ key, name }) => rowOf(key, name, stats.buckets[key]));
  const tested = rows.flatMap((r) => (r.result.kind === 'tested' ? [r.result] : []));
  if (tested.length === 0) return null;
  const axis = symmetricAxis(
    Math.max(...tested.flatMap((t) => [Math.abs(t.low), Math.abs(t.high), Math.abs(t.mean)])),
  );
  const anyFaded = tested.some((t) => t.faded);
  const x = (v: number) => ((v + axis.max) / (2 * axis.max)) * W;
  const mid = ROW_H / 2;
  const tickDigits = Number.isInteger(axis.max) ? 0 : 1;

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
              <Box sx={{ position: 'relative', height: ROW_H }}>
                <svg
                  viewBox={`0 0 ${String(W)} ${String(ROW_H)}`}
                  preserveAspectRatio="none"
                  width="100%"
                  height={ROW_H}
                  aria-hidden="true"
                  style={{ display: 'block' }}
                >
                  <Grid axis={axis} x={x} />
                  {t && (
                    <g data-testid={`bucket-bar-${r.key}`} opacity={t.faded ? FADE : 1}>
                      <rect
                        x={Math.min(x(0), x(t.mean))}
                        y={(ROW_H - BAR_H) / 2}
                        width={Math.max(1, Math.abs(x(t.mean) - x(0)))}
                        height={BAR_H}
                        fill={BAR_COLOR[directionOf(t.mean, 1)]}
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
                  )}
                </svg>
                {!t && (
                  <Typography
                    variant="caption"
                    sx={{
                      position: 'absolute',
                      top: '50%',
                      left: 4,
                      // Runs on into the value column so the sentence fits on one line.
                      right: `-${String(VALUE_COL)}px`,
                      transform: 'translateY(-50%)',
                      color: 'ink3',
                      bgcolor: 'bg',
                      px: 0.5,
                      width: 'fit-content',
                      maxWidth: `calc(100% + ${String(VALUE_COL)}px)`,
                    }}
                  >
                    {untestedText(r, stats.min_n)}
                  </Typography>
                )}
              </Box>
              {t && (
                <Typography variant="body2" sx={{ fontWeight: 600, textAlign: 'right' }}>
                  <Direction value={t.mean} />
                </Typography>
              )}
            </Box>
          );
        })}
        <Box sx={{ ...GRID, mt: 0.5 }} aria-hidden="true">
          <span />
          <Box sx={{ position: 'relative', height: 18 }}>
            {axis.ticks.map((v, i) => (
              <Typography
                key={v}
                variant="caption"
                sx={{
                  position: 'absolute',
                  left: `${String((x(v) / W) * 100)}%`,
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
                {v === 0 ? '0%' : pct(v, tickDigits)}
              </Typography>
            ))}
          </Box>
          <span />
        </Box>
      </Box>
      <Typography variant="caption" sx={{ display: 'block', color: 'ink3', mt: 1 }}>
        {anyFaded ? 'Faded: could be chance. ' : ''}Lines show the likely range.
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
