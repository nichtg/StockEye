import Box from '@mui/material/Box';
import type { Candle } from '../../api/types';
import { visuallyHidden } from '../../lib/a11y';
import type { Exchange } from '../../lib/exchange';
import { formatPrice, formatVolume } from '../../lib/format';
import { barLabel } from './tooltip';

const VISIBLE_BARS = 10;

interface Props {
  candles: Candle[];
  currency: string;
  exchange: Exchange;
  /** Spoken (politely) when the keyboard cursor moves to a bar. */
  announcement: string;
}

/** The latest bars as a real table, plus the live region, for people who cannot see the canvas. */
export function ChartA11yTable({ candles, currency, exchange, announcement }: Props) {
  const bars = candles.slice(-VISIBLE_BARS);
  const money = (v: number) => formatPrice(v, currency, exchange);
  return (
    <Box sx={visuallyHidden}>
      <table>
        <caption>Last {bars.length} bars</caption>
        <thead>
          <tr>
            <th>Date</th>
            <th>Open</th>
            <th>High</th>
            <th>Low</th>
            <th>Close</th>
            <th>Volume</th>
          </tr>
        </thead>
        <tbody>
          {bars.map((b) => (
            <tr key={b.time}>
              <td>{barLabel(b.time, exchange)}</td>
              <td>{money(b.open)}</td>
              <td>{money(b.high)}</td>
              <td>{money(b.low)}</td>
              <td>{money(b.close)}</td>
              <td>{formatVolume(b.volume, exchange)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div aria-live="polite">{announcement}</div>
    </Box>
  );
}
