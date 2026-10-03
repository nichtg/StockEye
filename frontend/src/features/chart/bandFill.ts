import type {
  IChartApiBase,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  LineData,
  SeriesType,
  SeriesAttachedParameter,
} from 'lightweight-charts';

export interface Band {
  lower: LineData[];
  color: string;
}

function lowerMap(band: Band) {
  return new Map<unknown, number>(band.lower.map((p) => [p.time, p.value]));
}

/**
 * Shades the area between the line it is attached to and `band.lower` (the Bollinger bands). The
 * chart has no band series, so this is a primitive attached to the upper line; both lines share
 * a price scale, so one series converts prices for both.
 */
export class BandFill implements ISeriesPrimitive {
  private chart: IChartApiBase | null = null;
  private series: ISeriesApi<SeriesType> | null = null;
  private requestUpdate: (() => void) | null = null;

  private lowerAt: Map<unknown, number>;

  constructor(
    private upper: LineData[],
    private band: Band,
  ) {
    this.lowerAt = lowerMap(band);
  }

  attached({ chart, series, requestUpdate }: SeriesAttachedParameter) {
    // The line series is the only thing this is ever attached to.
    this.chart = chart;
    this.series = series;
    this.requestUpdate = requestUpdate;
  }

  detached() {
    this.chart = this.series = this.requestUpdate = null;
  }

  update(upper: LineData[], band: Band) {
    this.upper = upper;
    this.band = band;
    this.lowerAt = lowerMap(band);
    this.requestUpdate?.();
  }

  private readonly view: IPrimitivePaneView = {
    zOrder: () => 'bottom',
    renderer: () => this.renderer,
  };

  paneViews() {
    return [this.view];
  }

  private readonly renderer: IPrimitivePaneRenderer = {
    draw: (target) => {
      const { chart, series } = this;
      if (!chart || !series) return;
      const xs: number[] = [];
      const tops: number[] = [];
      const bottoms: number[] = [];
      for (const p of this.upper) {
        const low = this.lowerAt.get(p.time);
        const x = chart.timeScale().timeToCoordinate(p.time);
        const top = series.priceToCoordinate(p.value);
        const bottom = low === undefined ? null : series.priceToCoordinate(low);
        if (x === null || top === null || bottom === null) continue;
        xs.push(x);
        tops.push(top);
        bottoms.push(bottom);
      }
      if (xs.length < 2) return;
      target.useBitmapCoordinateSpace(
        ({ context: c, horizontalPixelRatio: h, verticalPixelRatio: v }) => {
          c.beginPath();
          xs.forEach((x, i) => {
            if (i === 0) c.moveTo(x * h, (tops[i] ?? 0) * v);
            else c.lineTo(x * h, (tops[i] ?? 0) * v);
          });
          for (let i = xs.length - 1; i >= 0; i -= 1)
            c.lineTo((xs[i] ?? 0) * h, (bottoms[i] ?? 0) * v);
          c.closePath();
          c.fillStyle = this.band.color;
          c.fill();
        },
      );
    },
  };
}
