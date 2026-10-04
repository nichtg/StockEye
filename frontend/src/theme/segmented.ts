import { radius, type Tokens } from './tokens';

/**
 * The segmented-control look shared by the Technical/Macro tabs and other small switches: a grey
 * track with the chosen item raised in white. Unselected text is ink2, the lightest ink that still
 * meets WCAG AA on the track in light mode.
 */
export function segmentedStyles(t: Pick<Tokens, 'bg' | 'raised' | 'line' | 'ink' | 'ink2'>) {
  return {
    track: { backgroundColor: t.raised, borderRadius: radius.sm, padding: 4 },
    item: {
      minHeight: 32,
      borderRadius: 6,
      padding: '4px 16px',
      color: t.ink2,
      '&:hover': { color: t.ink },
    },
    selected: {
      color: t.ink,
      backgroundColor: t.bg,
      boxShadow: `inset 0 0 0 1px ${t.line}`,
    },
  } as const;
}
