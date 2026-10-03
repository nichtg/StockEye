import type { IChartApi, ISeriesApi, Logical } from 'lightweight-charts';
import { useEffect, useRef, useState, type KeyboardEvent, type RefObject } from 'react';
import type { ChartData } from '../../api/types';
import type { Exchange } from '../../lib/exchange';
import { barLabel, tooltipContent, type PatternSentences, type TooltipContent } from './tooltip';

export const TOOLTIP_WIDTH = 264;
export const TOOLTIP_GAP = 16;

export interface Tip {
  /** The data the bar came from: a tip for superseded data is not shown. */
  source: ChartData;
  index: number;
  x: number;
  /** Open to the left of the cursor instead of the right, when there is no room. */
  flip: boolean;
  content: TooltipContent;
}

interface Inputs {
  data: ChartData;
  currency: string;
  exchange: Exchange;
  sentences: PatternSentences;
}

/**
 * The bar under the pointer or keyboard cursor: drives the tooltip and the screen-reader
 * announcement. Arrow keys, Home and End move between bars; Escape or blur clears it.
 */
export function useChartCursor(
  chart: IChartApi | null,
  candles: ISeriesApi<'Candlestick'> | null,
  hostRef: RefObject<HTMLDivElement | null>,
  inputs: Inputs,
) {
  const [tip, setTip] = useState<Tip | null>(null);
  const [announce, setAnnounce] = useState('');
  const keyboardIndex = useRef<number | null>(null);
  // Event handlers read the latest inputs from here instead of being re-created with them.
  const latest = useRef(inputs);
  useEffect(() => {
    latest.current = inputs;
  });

  const tipAt = (index: number, x: number): Tip | null => {
    const { data, currency, exchange, sentences } = latest.current;
    const bar = data.candles[index];
    if (!bar) return null;
    const content = tooltipContent(
      bar,
      data.candles[index - 1],
      data.markers,
      { currency, exchange },
      sentences,
    );
    const room = hostRef.current?.clientWidth ?? Infinity;
    return { source: data, index, x, flip: x + TOOLTIP_GAP + TOOLTIP_WIDTH > room, content };
  };

  useEffect(() => {
    // Subscribed once per chart; the subscription goes away with the chart.
    chart?.subscribeCrosshairMove((param) => {
      if (param.point === undefined || param.logical === undefined || param.logical < 0) {
        if (keyboardIndex.current == null) setTip(null);
        return;
      }
      keyboardIndex.current = null;
      setTip(tipAt(Math.round(param.logical), param.point.x));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- tipAt reads only refs
  }, [chart]);

  const clear = () => {
    chart?.clearCrosshairPosition();
    keyboardIndex.current = null;
    setTip(null);
  };

  const showAt = (index: number) => {
    const bar = latest.current.data.candles[index];
    const point = candles?.dataByIndex(index);
    if (!chart || !candles || !bar || !point) return;
    keyboardIndex.current = index;
    chart.setCrosshairPosition(bar.close, point.time, candles);
    const next = tipAt(index, chart.timeScale().logicalToCoordinate(index as Logical) ?? 0);
    setTip(next);
    if (next) {
      const { open, high, low, close, events } = next.content;
      setAnnounce(
        `${barLabel(bar.time, latest.current.exchange)}: open ${open}, high ${high}, low ${low}, close ${close}. ${events.join('. ')}`,
      );
    }
  };

  const onKeyDown = (e: KeyboardEvent) => {
    const last = latest.current.data.candles.length - 1;
    if (last < 0) return;
    if (e.key === 'Escape') {
      clear();
      return;
    }
    const from = keyboardIndex.current;
    let next: number | null = null;
    if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = last;
    // The first arrow press lands on the latest bar, then moves from there.
    else if (e.key === 'ArrowLeft') next = from === null ? last : Math.max(0, from - 1);
    else if (e.key === 'ArrowRight') next = from === null ? last : Math.min(last, from + 1);
    if (next === null) return;
    e.preventDefault();
    showAt(next);
  };

  const onBlur = () => {
    if (keyboardIndex.current !== null) clear();
  };

  return {
    tip: tip?.source === inputs.data ? tip : null,
    announce,
    onKeyDown,
    onBlur,
  };
}
