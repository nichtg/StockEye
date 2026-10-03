import {
  ColorType,
  CrosshairMode,
  LineStyle,
  type DeepPartial,
  type ChartOptions,
  type Time,
} from 'lightweight-charts';
import { exchangeLocale, exchangeTimeZone, hour12For, type Exchange } from '../../lib/exchange';
import { dateFormat } from '../../lib/format';
import { FONT_FAMILY, type Tokens } from '../../theme/tokens';

function toDate(time: Time): Date {
  if (typeof time === 'number') return new Date(time * 1000);
  if (typeof time === 'string') return new Date(`${time}T00:00:00Z`);
  return new Date(Date.UTC(time.year, time.month - 1, time.day));
}

/** Axis and crosshair labels in the exchange's locale and zone. Daily bars are calendar dates. */
function timeLabels(exchange: Exchange, firstTime: string | number | undefined) {
  const locale = exchangeLocale(exchange);
  const zone = (time: Time) => (typeof time === 'number' ? exchangeTimeZone(exchange) : 'UTC');
  const clock = { hour: 'numeric', minute: '2-digit', hour12: hour12For(exchange) } as const;
  return {
    tickMarkFormatter: (time: Time, type: number) => {
      // A label centred on the very first bar would be cut by the left edge of the pane.
      if (time === firstTime) return '';
      const parts: Intl.DateTimeFormatOptions =
        typeof time === 'number' && type >= 3
          ? clock
          : type === 0
            ? { year: 'numeric' }
            : type === 1
              ? { month: 'short' }
              : { day: 'numeric', month: 'short' };
      return dateFormat(locale, { ...parts, timeZone: zone(time) }).format(toDate(time));
    },
    timeFormatter: (time: Time) =>
      dateFormat(locale, {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
        ...(typeof time === 'number' ? clock : {}),
        timeZone: zone(time),
      }).format(toDate(time)),
  };
}

export interface ChartLook {
  palette: Tokens;
  exchange: Exchange;
  height: number;
  intraday: boolean;
  /** Time of the first bar, whose axis label would be clipped. */
  firstTime: string | number | undefined;
}

export function chartOptions({
  palette,
  exchange,
  height,
  intraday,
  firstTime,
}: ChartLook): DeepPartial<ChartOptions> {
  const crosshairLine = {
    color: palette.ink3,
    style: LineStyle.Dashed,
    width: 1,
    labelBackgroundColor: palette.ink,
  } as const;
  const labels = timeLabels(exchange, firstTime);
  return {
    height,
    layout: {
      background: { type: ColorType.Solid, color: palette.raised },
      textColor: palette.ink3,
      fontFamily: FONT_FAMILY,
      fontSize: 12,
      // The TradingView logo overlaps the volume bars; attribution lives in the footer instead.
      attributionLogo: false,
      panes: {
        separatorColor: palette.line,
        separatorHoverColor: palette.line,
        enableResize: false,
      },
    },
    handleScale: { mouseWheel: false },
    handleScroll: { mouseWheel: false },
    grid: { vertLines: { visible: false }, horzLines: { color: palette.line } },
    crosshair: { mode: CrosshairMode.Normal, vertLine: crosshairLine, horzLine: crosshairLine },
    rightPriceScale: { borderVisible: false },
    timeScale: {
      borderVisible: false,
      timeVisible: intraday,
      secondsVisible: false,
      rightOffset: 2,
      fixLeftEdge: true,
      fixRightEdge: true,
      lockVisibleTimeRangeOnResize: true,
      tickMarkFormatter: labels.tickMarkFormatter,
    },
    localization: { locale: exchangeLocale(exchange), timeFormatter: labels.timeFormatter },
  };
}
