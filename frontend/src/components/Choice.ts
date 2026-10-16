/** One option of a single-choice control (segmented buttons or the themed select). */
export interface Choice {
  /** '' is "all" (or the default order). */
  value: string;
  label: string;
  /** Spoken name when the visible label is shortened ("October 2026" for "Oct 2026"). */
  name?: string;
  /** Undefined for "all": it has no meaningful count of its own. */
  count?: number;
}
