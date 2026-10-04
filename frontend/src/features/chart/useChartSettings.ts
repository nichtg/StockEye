import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router';
import type { RangeKey } from '../../api/types';
import {
  canonicalSelection,
  loadIndicatorSelection,
  saveIndicatorSelection,
  type IndicatorId,
} from './indicators';
import {
  MARKER_DEFS,
  loadMarkerOverrides,
  markerVisible,
  saveMarkerOverrides,
  type MarkerKind,
} from './markers';

export const RANGES: RangeKey[] = ['1W', '1M', '6M', '1Y', '2Y'];
const DEFAULT_RANGE: RangeKey = '6M';

function isRange(value: string | null): value is RangeKey {
  return RANGES.some((r) => r === value);
}

/**
 * The viewer's chart choices. Range and indicators live in the URL (`?range=6M&ind=sma50,vwap`)
 * so a link reproduces the view; with no `ind` in the URL the last indicators used are restored.
 * Indicator and marker choices are also remembered across visits.
 */
export function useChartSettings() {
  const [params, setParams] = useSearchParams();
  const [overrides, setOverrides] = useState(loadMarkerOverrides);

  const rangeParam = params.get('range');
  const range = isRange(rangeParam) ? rangeParam : DEFAULT_RANGE;
  const indParam = params.get('ind');
  const selection = useMemo(
    () => (indParam === null ? loadIndicatorSelection() : canonicalSelection(indParam.split(','))),
    [indParam],
  );
  const shownMarkers = useMemo(
    () => MARKER_DEFS.filter((m) => markerVisible(m.kind, range, overrides)).map((m) => m.kind),
    [range, overrides],
  );

  const setParam = (key: string, value: string) => {
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        next.set(key, value);
        return next;
      },
      { replace: true },
    );
  };

  // Two quick clicks can land before the URL change re-renders; the ref keeps the second one honest.
  const current = useRef(selection);
  useEffect(() => {
    current.current = selection;
  }, [selection]);

  const toggleIndicator = (id: IndicatorId) => {
    const from = current.current;
    const next = canonicalSelection(
      from.includes(id) ? from.filter((i) => i !== id) : [...from, id],
    );
    current.current = next;
    saveIndicatorSelection(next);
    setParam('ind', next.join(','));
  };

  const toggleMarker = (kind: MarkerKind) => {
    setOverrides((previous) => {
      const next = { ...previous, [kind]: !markerVisible(kind, range, previous) };
      saveMarkerOverrides(next);
      return next;
    });
  };

  return {
    range,
    setRange: (value: RangeKey) => {
      setParam('range', value);
    },
    selection,
    toggleIndicator,
    shownMarkers,
    toggleMarker,
  };
}
