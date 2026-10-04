import {
  LineStyle,
  createSeriesMarkers,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type SeriesType,
  type Time,
} from 'lightweight-charts';
import { useEffect, useRef, useState } from 'react';
import { BandFill } from './bandFill';
import { SUB_PANE_HEIGHT, type SeriesSpec, type SpecOf } from './model';

export interface Live {
  api: ISeriesApi<SeriesType>;
  spec: SeriesSpec;
  lines: IPriceLine[];
  fill?: BandFill;
}

function write(api: ISeriesApi<SeriesType>, spec: SeriesSpec) {
  api.applyOptions(spec.options);
  api.setData(spec.data);
  if (spec.scaleMargins) api.priceScale().applyOptions({ scaleMargins: spec.scaleMargins });
}

function writeLevelsAndBand(entry: Live, spec: SpecOf<'Line'>) {
  const { api } = entry;
  for (const line of entry.lines) api.removePriceLine(line);
  entry.lines = (spec.levels?.prices ?? []).map((price) =>
    api.createPriceLine({
      price,
      color: spec.levels?.color,
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: false,
      title: '',
    }),
  );
  if (!spec.band) return;
  if (entry.fill) entry.fill.update(spec.data, spec.band);
  else {
    entry.fill = new BandFill(spec.data, spec.band);
    api.attachPrimitive(entry.fill);
  }
}

function sameDeps(a: readonly unknown[], b: readonly unknown[]) {
  return a.length === b.length && a.every((x, i) => x === b[i]);
}

/**
 * The chart's live series, kept in line with a list of specs by key: new keys are added,
 * vanished ones removed, the rest updated only when their inputs changed. Nothing is torn down
 * wholesale, so the visible range is never disturbed.
 */
export class SeriesSet {
  readonly live = new Map<string, Live>();
  /** The candle series, typed, for markers and the crosshair readout. */
  candles: ISeriesApi<'Candlestick'> | null = null;

  sync(chart: IChartApi, specs: SeriesSpec[]) {
    const wanted = new Set(specs.map((s) => s.key));
    for (const [key, entry] of this.live) {
      if (wanted.has(key)) continue;
      chart.removeSeries(entry.api);
      this.live.delete(key);
      if (key === 'candles') this.candles = null;
    }
    for (const spec of specs) {
      let entry = this.live.get(spec.key);
      if (entry && entry.api.getPane().paneIndex() !== spec.pane) entry.api.moveToPane(spec.pane);
      if (entry && sameDeps(entry.spec.deps, spec.deps)) continue;
      entry ??= { api: this.add(chart, spec), spec, lines: [] };
      entry.spec = spec;
      this.live.set(spec.key, entry);
      write(entry.api, spec);
      if (spec.kind === 'Line') writeLevelsAndBand(entry, spec);
    }
  }

  private add(chart: IChartApi, spec: SeriesSpec): ISeriesApi<SeriesType> {
    if (spec.kind !== 'Candlestick') {
      return chart.addSeries(spec.definition, spec.options, spec.pane);
    }
    this.candles = chart.addSeries(spec.definition, spec.options, spec.pane);
    return this.candles;
  }

  clear() {
    this.live.clear(); // the chart is being removed along with its series
    this.candles = null;
  }
}

/**
 * Keeps the chart's series matching `specs` and returns the candle series. The chart is fitted
 * to the content only when `fitKey` changes (a new symbol or range), never when indicators toggle.
 */
export function useChartSeries(
  chart: IChartApi | null,
  specs: SeriesSpec[],
  baseHeight: number,
  fitKey: string,
): ISeriesApi<'Candlestick'> | null {
  const set = useRef(new SeriesSet());
  const fitted = useRef<string | null>(null);
  const [candles, setCandles] = useState<ISeriesApi<'Candlestick'> | null>(null);

  useEffect(() => {
    if (!chart) return;
    const kept = fitted.current === fitKey ? chart.timeScale().getVisibleLogicalRange() : null;
    set.current.sync(chart, specs);
    // Stretch factors are proportional, so pixel heights (420 : 100 : 100) give the split.
    chart.panes().forEach((pane, i) => {
      pane.setStretchFactor(i === 0 ? baseHeight : SUB_PANE_HEIGHT);
    });
    if (kept) {
      // Adding a pane makes the chart re-anchor to the latest bar; put the viewer's zoom back.
      chart.timeScale().setVisibleLogicalRange(kept);
    } else {
      chart.timeScale().fitContent();
      fitted.current = fitKey;
    }
    setCandles(set.current.candles);
  }, [chart, specs, baseHeight, fitKey]);

  useEffect(() => {
    const current = set.current;
    return () => {
      current.clear();
      fitted.current = null;
    };
  }, [chart]);

  return candles;
}

/** Shows `markers` on the series through its own plugin, so toggling them touches nothing else. */
export function useSeriesMarkers(
  series: ISeriesApi<'Candlestick'> | null,
  markers: SeriesMarker<Time>[],
) {
  const plugin = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  useEffect(() => {
    plugin.current = series ? createSeriesMarkers(series, []) : null;
  }, [series]);
  useEffect(() => {
    plugin.current?.setMarkers(markers);
  }, [series, markers]);
}
