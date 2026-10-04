import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import { useState, type KeyboardEvent } from 'react';
import type { MacroReportOut } from '../../api/types';
import { visuallyHidden } from '../../lib/a11y';
import type { Exchange } from '../../lib/exchange';
import { formatDate, formatSigned } from '../../lib/format';
import { radius } from '../../theme/tokens';

type Point = MacroReportOut['timeline'][number];

/** Drawing units. The SVG stretches to its column (`preserveAspectRatio="none"`). */
const WIDTH = 1000;
const HEIGHT = 120;
const GAP = 2; // between bars
const PAD = 14; // room for the axis captions
const MIN_ARTICLES = 3;

/** Value at fraction q of the sorted list (linear interpolation). */
function quantile(sorted: number[], q: number): number {
  if (sorted.length === 0) return 0;
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return (sorted[lo] ?? 0) + ((sorted[hi] ?? 0) - (sorted[lo] ?? 0)) * (pos - lo);
}

const articles = (n: number) => `${String(n)} ${n === 1 ? 'article' : 'articles'}`;

interface Props {
  points: Point[];
  exchange: Exchange;
}

/**
 * Weekly average news sentiment as bars from a zero baseline: positive in ink, negative in a
 * lighter ink. The scale ends at the 95th percentile of |score| so one outlier week cannot flatten
 * the rest; taller bars are clipped at the edge and marked with a cap tick. Weeks backed by fewer
 * than 3 articles are faded. The chart is one slider: hover, tap or arrow keys pick a week, and
 * every week is also in a hidden table.
 */
export function WeeklySentiment({ points, exchange }: Props) {
  const [active, setActive] = useState<number | null>(null);
  const count = points.length;
  if (count === 0) return null;

  const values = points.map((p) => p.mean_score);
  const limit =
    quantile(
      values.map((v) => Math.abs(v)).sort((x, y) => x - y),
      0.95,
    ) || 1e-6;
  const top = Math.min(Math.max(0, ...values), limit);
  const bottom = Math.max(Math.min(0, ...values), -limit);
  const span = top - bottom || 1;
  const plotH = HEIGHT - PAD * 2;
  const y = (v: number) => PAD + ((top - Math.min(top, Math.max(bottom, v))) / span) * plotH;
  const zeroY = y(0);
  const slot = WIDTH / count;
  const barW = Math.max(1, slot - GAP);
  const selected = active == null ? undefined : points[active];
  const current = selected ?? points.at(-1);
  const first = points[0];
  const last = points.at(-1);

  const weekEnding = (p: Point) => formatDate(p.week_end, exchange);
  const describe = (p: Point) =>
    `Week ending ${weekEnding(p)}: average sentiment ${formatSigned(p.mean_score, 2)}, ${articles(p.article_count)}`;

  const onKeyDown = (e: KeyboardEvent) => {
    const from = active ?? count - 1;
    const next =
      e.key === 'ArrowLeft'
        ? from - 1
        : e.key === 'ArrowRight'
          ? from + 1
          : e.key === 'Home'
            ? 0
            : e.key === 'End'
              ? count - 1
              : null;
    if (next == null) return;
    e.preventDefault();
    setActive(Math.min(count - 1, Math.max(0, next)));
  };

  return (
    <Box>
      <Box
        role="slider"
        tabIndex={0}
        aria-label="Weekly news sentiment. Use the arrow keys to move between weeks."
        aria-orientation="horizontal"
        aria-valuemin={0}
        aria-valuemax={count - 1}
        aria-valuenow={active ?? count - 1}
        aria-valuetext={current && describe(current)}
        onKeyDown={onKeyDown}
        onFocus={() => {
          setActive((a) => a ?? count - 1);
        }}
        onBlur={() => {
          setActive(null);
        }}
        onMouseLeave={() => {
          setActive(null);
        }}
        sx={{
          position: 'relative',
          borderRadius: radius.sm,
          '&:focus-visible': { outlineOffset: 4 },
        }}
      >
        <svg
          viewBox={`0 0 ${String(WIDTH)} ${String(HEIGHT)}`}
          preserveAspectRatio="none"
          width="100%"
          height={HEIGHT}
          aria-hidden="true"
          style={{ display: 'block' }}
        >
          <line
            x1={0}
            x2={WIDTH}
            y1={zeroY}
            y2={zeroY}
            stroke="var(--se-line)"
            strokeWidth={1}
            vectorEffect="non-scaling-stroke"
          />
          {points.map((p, i) => {
            const v = y(p.mean_score);
            const x = i * slot + (slot - barW) / 2;
            const clipped = p.mean_score > top || p.mean_score < bottom;
            const capY = p.mean_score > 0 ? v + 3 : v - 3;
            return (
              <g
                key={p.week_end}
                opacity={active === i || p.article_count >= MIN_ARTICLES ? 1 : 0.4}
              >
                <rect
                  x={x}
                  y={Math.min(v, zeroY)}
                  width={barW}
                  height={Math.max(1, Math.abs(v - zeroY))}
                  fill={p.mean_score >= 0 ? 'var(--se-ink)' : 'var(--se-ink3)'}
                />
                {clipped && (
                  <line
                    x1={x}
                    x2={x + barW}
                    y1={capY}
                    y2={capY}
                    stroke="var(--se-bg)"
                    strokeWidth={1.5}
                    vectorEffect="non-scaling-stroke"
                  />
                )}
              </g>
            );
          })}
          {points.map((p, i) => (
            <rect
              key={`hit-${p.week_end}`}
              x={i * slot}
              y={0}
              width={slot}
              height={HEIGHT}
              fill="transparent"
              onMouseEnter={() => {
                setActive(i);
              }}
              onClick={() => {
                setActive(i);
              }}
            />
          ))}
        </svg>
        <Typography
          variant="caption"
          aria-hidden="true"
          sx={{ position: 'absolute', left: 0, top: -2, color: 'ink3', pointerEvents: 'none' }}
        >
          More positive
        </Typography>
        <Typography
          variant="caption"
          aria-hidden="true"
          sx={{ position: 'absolute', left: 0, bottom: -2, color: 'ink3', pointerEvents: 'none' }}
        >
          More negative
        </Typography>
        {selected && active != null && (
          <Box
            aria-hidden="true"
            data-testid="sentiment-tooltip"
            sx={{
              position: 'absolute',
              top: 0,
              left: `${String(((active + 0.5) / count) * 100)}%`,
              transform: active > count / 2 ? 'translateX(-105%)' : 'translateX(8px)',
              bgcolor: 'raised',
              border: 1,
              borderColor: 'line',
              borderRadius: radius.sm,
              px: 1.5,
              py: 1,
              pointerEvents: 'none',
              whiteSpace: 'nowrap',
              boxShadow: 'var(--se-shadow)',
              zIndex: 1,
            }}
          >
            <Typography variant="caption" sx={{ display: 'block', color: 'ink3' }}>
              Week ending {weekEnding(selected)}
            </Typography>
            <Typography variant="body2" sx={{ color: 'ink' }}>
              Average sentiment {formatSigned(selected.mean_score, 2)}
            </Typography>
            <Typography variant="body2">{articles(selected.article_count)}</Typography>
          </Box>
        )}
      </Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 0.5, color: 'ink3' }}>
        <Typography variant="caption">
          {first && formatDate(first.week_end, exchange, { month: 'short', year: 'numeric' })}
        </Typography>
        <Typography variant="caption">
          {last && formatDate(last.week_end, exchange, { month: 'short', year: 'numeric' })}
        </Typography>
      </Box>
      <Typography variant="caption" sx={{ display: 'block', color: 'ink3', mt: 0.5 }}>
        Faded: fewer than {MIN_ARTICLES} articles
      </Typography>
      <Box sx={visuallyHidden}>
        <table>
          <caption>Weekly news sentiment, all weeks</caption>
          <thead>
            <tr>
              <th>Week ending</th>
              <th>Average sentiment</th>
              <th>Articles</th>
            </tr>
          </thead>
          <tbody>
            {points.map((p) => (
              <tr key={p.week_end}>
                <td>{weekEnding(p)}</td>
                <td>{formatSigned(p.mean_score, 2)}</td>
                <td>{p.article_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Box>
    </Box>
  );
}
