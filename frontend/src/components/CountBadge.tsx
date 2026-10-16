import Box from '@mui/material/Box';

/**
 * The count after a choice's name ("Singapore [1]"): a small pill with a 1px line border. The text
 * is ink2, which measures 9.7:1 on the raised track and 10.5:1 on bg in light mode (10.4:1 and
 * 12.0:1 in dark). `inverted` is for the chosen item: bg text on an ink fill, 21:1 in both modes.
 * It is an inline block so its text sits on the same baseline as the name beside it.
 */
export function CountBadge({ count, inverted = false }: { count: number; inverted?: boolean }) {
  return (
    <Box
      component="span"
      className="count-badge"
      data-inverted={inverted}
      sx={{
        display: 'inline-block',
        flexShrink: 0,
        px: '6px',
        py: '1px',
        border: 1,
        borderColor: inverted ? 'ink' : 'line',
        borderRadius: '999px',
        backgroundColor: inverted ? 'ink' : 'transparent',
        color: inverted ? 'bg' : 'ink2',
        fontSize: '0.75rem',
        fontWeight: 500,
        lineHeight: 1,
        fontVariantNumeric: 'tabular-nums',
      }}
    >
      {count}
    </Box>
  );
}
