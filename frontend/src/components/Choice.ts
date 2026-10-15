/** One option of a single-choice control (segmented buttons or the themed select). */
export interface Choice {
  /** '' is "all" (or the default order). */
  value: string;
  label: string;
  /** Undefined for "all": it has no meaningful count of its own. */
  count?: number;
}

/**
 * Counts sit in ink2, not ink3: ink3 on the raised track and menu hover measures about 4.2:1,
 * under AA. Weight and size set them apart from the label instead.
 */
export const countSx = {
  color: 'ink2',
  fontWeight: 400,
  fontSize: '0.8125rem',
  fontVariantNumeric: 'tabular-nums',
} as const;
