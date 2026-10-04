interface SparklineProps {
  values: number[];
  width?: number;
  height?: number;
}

/** A 96x28 trend line in ink2 with an end dot: no axes, no fill, decorative (aria-hidden). */
export function Sparkline({ values, width = 96, height = 28 }: SparklineProps) {
  if (values.length < 2) {
    return <svg width={width} height={height} aria-hidden="true" data-testid="sparkline-empty" />;
  }
  const pad = 3;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const x = (i: number) => pad + (i / (values.length - 1)) * (width - pad * 2);
  const y = (v: number) => height - pad - ((v - min) / span) * (height - pad * 2);
  const d = values
    .map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)} ${y(v).toFixed(1)}`)
    .join(' ');
  const lastX = x(values.length - 1);
  const lastY = y(values[values.length - 1] ?? min);
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden="true"
      focusable="false"
      data-testid="sparkline"
      style={{ display: 'block', overflow: 'visible' }}
    >
      <path
        d={d}
        fill="none"
        stroke="var(--se-ink2)"
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx={lastX} cy={lastY} r={2.5} fill="var(--se-ink)" />
    </svg>
  );
}
