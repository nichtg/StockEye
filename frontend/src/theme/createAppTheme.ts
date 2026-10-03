import { alpha, createTheme, type Theme } from '@mui/material/styles';
import { FONT_FAMILY, MOTION_MS, tokens, type ColorMode } from './tokens';

const TRANSITION = `${MOTION_MS}ms ease`;

/**
 * Builds the StockEye theme for one colour mode. `cssVariables: true` exposes every palette key
 * (including the custom ink/line/up/down tokens) as `--mui-palette-*` variables for chart code.
 */
export function createAppTheme(mode: ColorMode): Theme {
  const t = tokens[mode];
  const shadow = mode === 'light' ? '0 4px 16px rgba(0,0,0,.12)' : 'none';
  const focusRing = { outline: `2px solid ${t.ink}`, outlineOffset: 2 } as const;

  return createTheme({
    cssVariables: true,
    spacing: 8,
    shape: { borderRadius: 8 },
    palette: {
      mode,
      ...t,
      primary: { main: t.ink, contrastText: t.bg },
      secondary: { main: t.ink2, contrastText: t.bg },
      // Warning and info stay in ink: colour means direction (up/down) plus errors and destructive
      // actions (down), and the latter two always come with an icon and a word.
      warning: { main: t.ink, contrastText: t.bg },
      info: { main: t.ink2, contrastText: t.bg },
      error: { main: t.down, contrastText: t.bg },
      success: { main: t.up, contrastText: t.bg },
      background: { default: t.bg, paper: t.bg },
      text: { primary: t.ink2, secondary: t.ink3, disabled: t.ink3 },
      divider: t.line,
      action: {
        active: t.ink,
        hover: alpha(t.ink, 0.06),
        selected: alpha(t.ink, 0.1),
        focus: alpha(t.ink, 0.12),
        disabled: t.ink3,
        disabledBackground: t.raised,
      },
    },
    typography: {
      fontFamily: FONT_FAMILY,
      fontWeightRegular: 400,
      fontWeightMedium: 500,
      fontWeightBold: 600,
      display: {
        fontSize: '2.5rem',
        lineHeight: 1.1,
        fontWeight: 500,
        letterSpacing: '-0.02em',
        color: t.ink,
      },
      h1: { fontSize: '1.5rem', lineHeight: 1.25, fontWeight: 600, color: t.ink },
      h2: { fontSize: '1.125rem', lineHeight: 1.35, fontWeight: 600, color: t.ink },
      h3: { fontSize: '1rem', lineHeight: 1.4, fontWeight: 600, color: t.ink },
      h4: { fontSize: '0.9375rem', lineHeight: 1.45, fontWeight: 600, color: t.ink },
      h5: { fontSize: '0.9375rem', lineHeight: 1.45, fontWeight: 600, color: t.ink },
      h6: { fontSize: '0.9375rem', lineHeight: 1.45, fontWeight: 600, color: t.ink },
      body1: { fontSize: '0.9375rem', lineHeight: 1.55, fontWeight: 400 },
      body2: { fontSize: '0.8125rem', lineHeight: 1.45, fontWeight: 400 }, // "small"
      subtitle1: { fontSize: '0.9375rem', lineHeight: 1.55, fontWeight: 500 },
      subtitle2: { fontSize: '0.8125rem', lineHeight: 1.45, fontWeight: 500 },
      caption: { fontSize: '0.75rem', lineHeight: 1.4, fontWeight: 500 },
      button: {
        fontSize: '0.9375rem',
        lineHeight: 1.4,
        fontWeight: 500,
        textTransform: 'none',
        letterSpacing: 0,
      },
      overline: { textTransform: 'none', letterSpacing: 0, fontSize: '0.75rem', fontWeight: 500 },
    },
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          ':root': {
            // Short aliases for chart code and plain CSS.
            '--se-bg': 'var(--mui-palette-bg)',
            '--se-raised': 'var(--mui-palette-raised)',
            '--se-line': 'var(--mui-palette-line)',
            '--se-ink': 'var(--mui-palette-ink)',
            '--se-ink2': 'var(--mui-palette-ink2)',
            '--se-ink3': 'var(--mui-palette-ink3)',
            '--se-up': 'var(--mui-palette-up)',
            '--se-down': 'var(--mui-palette-down)',
            '--se-shadow': shadow,
          },
          html: { scrollPaddingTop: '72px' },
          body: {
            fontVariantNumeric: 'tabular-nums',
            WebkitFontSmoothing: 'antialiased',
            textRendering: 'optimizeLegibility',
          },
          ':focus-visible': focusRing,
          '::selection': { backgroundColor: t.ink, color: t.bg },
          a: { touchAction: 'manipulation' },
          'button, [role="button"]': { touchAction: 'manipulation' },
          '@media (prefers-reduced-motion: reduce)': {
            '*, *::before, *::after': {
              animationDuration: '0.01ms !important',
              animationIterationCount: '1 !important',
              transitionDuration: '0.01ms !important',
              scrollBehavior: 'auto !important',
            },
          },
        },
      },
      MuiButtonBase: {
        defaultProps: { disableRipple: true },
        styleOverrides: {
          root: {
            '&.Mui-focusVisible': focusRing,
            transition: `background-color ${TRANSITION}, border-color ${TRANSITION}, color ${TRANSITION}`,
          },
        },
      },
      MuiButton: {
        defaultProps: { disableElevation: true },
        styleOverrides: {
          root: { borderRadius: 8, minHeight: 40, padding: '8px 16px', boxShadow: 'none' },
          sizeSmall: { minHeight: 32, padding: '4px 12px', fontSize: '0.8125rem' },
          sizeLarge: { minHeight: 48 },
          containedPrimary: {
            backgroundColor: t.ink,
            color: t.bg,
            '&:hover': { backgroundColor: t.ink2, boxShadow: 'none' },
            '&.Mui-disabled': { backgroundColor: t.line, color: t.ink3 },
          },
          containedError: {
            backgroundColor: t.down,
            color: t.bg,
            '&:hover': { backgroundColor: t.down, filter: 'brightness(0.92)', boxShadow: 'none' },
          },
          outlinedPrimary: {
            color: t.ink,
            borderColor: t.ink3,
            '&:hover': { borderColor: t.ink, backgroundColor: t.raised },
            '&.Mui-disabled': { borderColor: t.line, color: t.ink3 },
          },
          textPrimary: {
            color: t.ink,
            '&:hover': { backgroundColor: t.raised },
          },
        },
      },
      MuiIconButton: {
        styleOverrides: {
          root: { color: t.ink, '&:hover': { backgroundColor: t.raised } },
        },
      },
      MuiLink: {
        defaultProps: { underline: 'always' },
        styleOverrides: {
          root: {
            color: t.ink,
            textDecorationColor: t.ink3,
            textUnderlineOffset: '0.2em',
            '&:hover': { textDecorationColor: t.ink },
          },
        },
      },
      MuiTextField: { defaultProps: { variant: 'outlined', size: 'medium' } },
      MuiFormLabel: {
        // Fields are marked required for assistive tech; the visual asterisk is just noise here.
        styleOverrides: { asterisk: { display: 'none' } },
      },
      MuiInputLabel: {
        styleOverrides: {
          root: {
            color: t.ink3,
            '&.Mui-focused': { color: t.ink },
            '&.Mui-error': { color: t.down },
          },
        },
      },
      MuiOutlinedInput: {
        styleOverrides: {
          root: {
            borderRadius: 8,
            backgroundColor: t.bg,
            '& .MuiOutlinedInput-notchedOutline': {
              borderColor: t.line,
              transition: `border-color ${TRANSITION}`,
            },
            '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: t.ink3 },
            '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
              borderColor: t.ink,
              borderWidth: 2,
            },
            '&.Mui-error .MuiOutlinedInput-notchedOutline': { borderColor: t.down },
            '&.Mui-disabled': { backgroundColor: t.raised },
            '&.Mui-disabled .MuiOutlinedInput-notchedOutline': { borderColor: t.line },
          },
          input: {
            '&::placeholder': { color: t.ink3, opacity: 1 },
            '&.Mui-disabled': { WebkitTextFillColor: t.ink3 },
          },
        },
      },
      MuiFormHelperText: {
        styleOverrides: {
          root: {
            marginLeft: 0,
            fontSize: '0.8125rem',
            lineHeight: 1.45,
            color: t.ink3,
            '&.Mui-error': { color: t.down },
          },
        },
      },
      MuiChip: {
        styleOverrides: {
          root: {
            borderRadius: 8,
            fontWeight: 500,
            fontSize: '0.75rem',
            color: t.ink,
            backgroundColor: t.raised,
            border: `1px solid ${t.line}`,
          },
          outlined: { backgroundColor: 'transparent', borderColor: t.ink3 },
          clickable: { '&:hover': { backgroundColor: t.line } },
        },
      },
      MuiTabs: {
        styleOverrides: {
          root: { minHeight: 40, backgroundColor: t.raised, borderRadius: 8, padding: 4 },
          indicator: { display: 'none' },
        },
      },
      MuiTab: {
        styleOverrides: {
          root: {
            minHeight: 32,
            borderRadius: 6,
            padding: '4px 16px',
            color: t.ink3,
            '&.Mui-selected': {
              color: t.ink,
              backgroundColor: t.bg,
              boxShadow: `inset 0 0 0 1px ${t.line}`,
            },
            '&:hover': { color: t.ink },
          },
        },
      },
      MuiTable: { defaultProps: { size: 'small' } },
      MuiTableHead: {
        styleOverrides: { root: { backgroundColor: t.raised } },
      },
      MuiTableCell: {
        styleOverrides: {
          root: {
            borderBottom: `1px solid ${t.line}`,
            padding: '12px 16px',
            fontSize: '0.8125rem',
            lineHeight: 1.45,
            color: t.ink2,
            fontVariantNumeric: 'tabular-nums',
          },
          head: { color: t.ink, fontWeight: 600, whiteSpace: 'nowrap' },
        },
      },
      MuiTablePagination: {
        styleOverrides: {
          root: { color: t.ink2, fontSize: '0.8125rem' },
          displayedRows: { fontSize: '0.8125rem', fontVariantNumeric: 'tabular-nums' },
        },
      },
      MuiTooltip: {
        defaultProps: { arrow: false, enterDelay: 100 },
        styleOverrides: {
          tooltip: {
            backgroundColor: t.bg,
            color: t.ink2,
            border: `1px solid ${t.line}`,
            borderRadius: 8,
            boxShadow: shadow,
            fontSize: '0.8125rem',
            lineHeight: 1.45,
            fontWeight: 400,
            padding: '8px 12px',
            maxWidth: 300,
          },
        },
      },
      MuiPopover: {
        styleOverrides: {
          paper: { border: `1px solid ${t.line}`, boxShadow: shadow, backgroundImage: 'none' },
        },
      },
      MuiMenu: {
        styleOverrides: {
          paper: {
            borderRadius: 8,
            border: `1px solid ${t.line}`,
            boxShadow: shadow,
            backgroundImage: 'none',
          },
        },
      },
      MuiMenuItem: {
        styleOverrides: {
          root: {
            fontSize: '0.9375rem',
            minHeight: 40,
            color: t.ink2,
            '&:hover, &.Mui-focusVisible': { backgroundColor: t.raised, color: t.ink },
            '&.Mui-focusVisible': { outline: `2px solid ${t.ink}`, outlineOffset: -2 },
          },
        },
      },
      MuiPaper: {
        styleOverrides: { root: { backgroundImage: 'none', boxShadow: 'none' } },
      },
      MuiDialog: {
        styleOverrides: {
          paper: { borderRadius: 12, border: `1px solid ${t.line}`, boxShadow: shadow },
        },
      },
      MuiDialogTitle: {
        styleOverrides: {
          root: { fontSize: '1.125rem', lineHeight: 1.35, fontWeight: 600, color: t.ink },
        },
      },
      MuiAlert: {
        defaultProps: { variant: 'standard' },
        styleOverrides: {
          root: {
            borderRadius: 8,
            border: `1px solid ${t.line}`,
            backgroundColor: t.raised,
            color: t.ink2,
            fontSize: '0.9375rem',
            alignItems: 'flex-start',
          },
          standardWarning: { borderColor: t.ink, '& .MuiAlert-icon': { color: t.ink } },
          standardError: { borderColor: t.down, '& .MuiAlert-icon': { color: t.down } },
          standardInfo: { '& .MuiAlert-icon': { color: t.ink2 } },
          standardSuccess: { '& .MuiAlert-icon': { color: t.ink } },
          message: { padding: '6px 0' },
        },
      },
      MuiSnackbarContent: {
        styleOverrides: {
          root: {
            backgroundColor: t.ink,
            color: t.bg,
            borderRadius: 8,
            boxShadow: 'none',
            fontSize: '0.9375rem',
          },
        },
      },
      MuiSkeleton: {
        defaultProps: { animation: 'pulse' },
        styleOverrides: { root: { backgroundColor: t.line } },
      },
      MuiLinearProgress: {
        styleOverrides: {
          root: { height: 4, borderRadius: 999, backgroundColor: t.line },
          bar: { borderRadius: 999 },
          barColorPrimary: { backgroundColor: t.ink },
        },
      },
      MuiAvatar: {
        styleOverrides: {
          root: {
            backgroundColor: t.raised,
            color: t.ink,
            border: `1px solid ${t.line}`,
            fontSize: '0.8125rem',
            fontWeight: 600,
          },
        },
      },
      MuiDivider: { styleOverrides: { root: { borderColor: t.line } } },
    },
  });
}
