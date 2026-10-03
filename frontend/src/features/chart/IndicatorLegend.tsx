import { LineStyle } from 'lightweight-charts';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import type { RangeKey } from '../../api/types';
import { Term } from '../../components/Term';
import { INDICATORS, dashArray, vwapVariant, type IndicatorId } from './indicators';

/** Key to the lines on the chart; each swatch is drawn from the same definition as its series. */
export function IndicatorLegend({
  selection,
  range,
}: {
  selection: IndicatorId[];
  range: RangeKey;
}) {
  const active = INDICATORS.filter((i) => selection.includes(i.id));
  if (active.length === 0) return null;
  return (
    <Box
      sx={{ display: 'flex', flexWrap: 'wrap', columnGap: 2.5, rowGap: 0.5, mb: 1.5 }}
      aria-label="Indicator legend"
    >
      {active.map((ind) => {
        const { label, term } = ind.id === 'vwap' ? vwapVariant(range) : ind;
        const dash = dashArray(ind.lineStyle);
        return (
          <Typography
            key={ind.id}
            variant="body2"
            component="span"
            sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.75, color: 'ink2' }}
          >
            <svg width="24" height="10" aria-hidden="true" focusable="false">
              <line
                x1="1"
                y1="5"
                x2="23"
                y2="5"
                stroke={`var(--se-${ind.tone})`}
                strokeWidth={ind.width}
                strokeDasharray={dash}
                strokeLinecap={ind.lineStyle === LineStyle.Dotted ? 'round' : 'butt'}
              />
            </svg>
            <Term id={term}>{label}</Term>
          </Typography>
        );
      })}
    </Box>
  );
}
