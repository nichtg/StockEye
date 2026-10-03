import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import { Direction } from '../../components/Direction';
import { radius } from '../../theme/tokens';
import { formatPct } from '../../lib/format';
import { TOOLTIP_GAP, TOOLTIP_WIDTH, type Tip } from './useChartCursor';

/** Pointer-transparent readout for one bar; screen readers get the same facts another way. */
export function ChartTooltip({ tip, label }: { tip: Tip; label: string }) {
  const { content } = tip;
  return (
    <Box
      aria-hidden="true"
      data-testid="chart-tooltip"
      sx={{
        position: 'absolute',
        top: 12,
        left: tip.x + TOOLTIP_GAP,
        width: TOOLTIP_WIDTH,
        transform: tip.flip ? `translateX(calc(-100% - ${2 * TOOLTIP_GAP}px))` : 'none',
        pointerEvents: 'none',
        bgcolor: 'raised',
        border: 1,
        borderColor: 'line',
        borderRadius: radius.sm,
        boxShadow: 'var(--se-shadow)',
        p: 1.5,
        zIndex: 2,
      }}
    >
      <Typography variant="caption" sx={{ color: 'ink3', display: 'block', mb: 0.5 }}>
        {label}
      </Typography>
      <Box
        component="dl"
        sx={{
          display: 'grid',
          gridTemplateColumns: 'auto 1fr auto 1fr',
          columnGap: 1,
          rowGap: 0.25,
          m: 0,
          fontSize: '0.8125rem',
          fontVariantNumeric: 'tabular-nums',
          '& dt': { color: 'ink3' },
          '& dd': { m: 0, color: 'ink', textAlign: 'right' },
        }}
      >
        <dt>Open</dt>
        <dd>{content.open}</dd>
        <dt>High</dt>
        <dd>{content.high}</dd>
        <dt>Low</dt>
        <dd>{content.low}</dd>
        <dt>Close</dt>
        <dd>{content.close}</dd>
      </Box>
      <Box
        sx={{ display: 'flex', justifyContent: 'space-between', mt: 0.75, fontSize: '0.8125rem' }}
      >
        <Direction
          value={content.changePct}
          digits={2}
          text={`${content.change} (${formatPct(content.changePct, { signed: true, digits: 2 })})`}
        />
        <Box component="span" sx={{ color: 'ink3' }}>
          Vol {content.volume}
        </Box>
      </Box>
      {content.events.map((text) => (
        <Typography
          key={text}
          variant="body2"
          sx={{ mt: 0.75, pt: 0.75, borderTop: 1, borderColor: 'line', color: 'ink2' }}
        >
          {text}
        </Typography>
      ))}
    </Box>
  );
}
