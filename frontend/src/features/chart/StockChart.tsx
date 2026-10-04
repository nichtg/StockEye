import Box from '@mui/material/Box';
import Skeleton from '@mui/material/Skeleton';
import Typography from '@mui/material/Typography';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useTheme } from '@mui/material/styles';
import { useEffect, useMemo } from 'react';
import type { FullStatuses, StockOut } from '../../api/types';
import { QueryRegion } from '../../components/QueryRegion';
import { exchangeCurrency, exchangeOfSymbol } from '../../lib/exchange';
import { radius } from '../../theme/tokens';
import { usePatternReliability } from '../stock/usePatternReliability';
import { useChart } from '../stock/useStockData';
import { ChartToolbar } from './ChartToolbar';
import { IndicatorLegend } from './IndicatorLegend';
import { MarkerKey } from './MarkerKey';
import { markerCounts } from './markers';
import { PriceChart } from './PriceChart';
import { useChartSettings } from './useChartSettings';

export const HEIGHT_DESKTOP = 420;
export const HEIGHT_MOBILE = 300;

interface Props {
  symbol: string;
  stock: StockOut | undefined;
  /** Reports the chart data's freshness (prices, events and news), for the page's status line. */
  onStatus: (status: FullStatuses | undefined) => void;
}

/** The price chart with its controls. Owns the range, indicator and marker choices. */
export function StockChart({ symbol, stock, onStatus }: Props) {
  const compact = useMediaQuery(useTheme().breakpoints.down('sm'));
  const baseHeight = compact ? HEIGHT_MOBILE : HEIGHT_DESKTOP;
  const settings = useChartSettings();
  const chart = useChart(symbol, settings.range);
  const sentences = usePatternReliability(symbol);

  const status = chart.data?.data_status;
  useEffect(() => {
    onStatus(status);
  }, [onStatus, status]);

  const markers = chart.data?.markers;
  const counts = useMemo(() => (markers ? markerCounts(markers) : undefined), [markers]);

  const exchange = stock?.exchange ?? exchangeOfSymbol(symbol);
  const currency = stock?.currency ?? exchangeCurrency(exchange);

  return (
    <Box>
      <ChartToolbar
        range={settings.range}
        onRangeChange={settings.setRange}
        selection={settings.selection}
        onToggleIndicator={settings.toggleIndicator}
      />
      <IndicatorLegend selection={settings.selection} range={settings.range} />

      <QueryRegion
        query={chart}
        errorTitle="We couldn’t load the chart"
        skeleton={
          <Skeleton
            variant="rounded"
            height={baseHeight}
            role="status"
            aria-label="Loading chart…"
            sx={{ borderRadius: radius.lg }}
          />
        }
      >
        {(data) =>
          data.candles.length === 0 ? (
            <Box
              sx={{
                height: baseHeight,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: 1,
                borderColor: 'line',
                borderRadius: radius.lg,
                bgcolor: 'raised',
              }}
            >
              <Typography sx={{ color: 'ink2' }}>No trading data for this period.</Typography>
            </Box>
          ) : (
            // Dimmed while the next range loads; the previous bars stay until it arrives.
            <Box
              sx={{ opacity: chart.isPlaceholderData ? 0.6 : 1, transition: 'opacity 150ms ease' }}
            >
              <PriceChart
                data={data}
                selection={settings.selection}
                currency={currency}
                exchange={exchange}
                baseHeight={baseHeight}
                sentences={sentences}
                shownMarkers={settings.shownMarkers}
              />
            </Box>
          )
        }
      </QueryRegion>

      <MarkerKey shown={settings.shownMarkers} counts={counts} onToggle={settings.toggleMarker} />
    </Box>
  );
}
