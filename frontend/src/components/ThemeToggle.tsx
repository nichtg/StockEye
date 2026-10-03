import DarkModeOutlined from '@mui/icons-material/DarkModeOutlined';
import LightModeOutlined from '@mui/icons-material/LightModeOutlined';
import IconButton from '@mui/material/IconButton';
import { useColorMode } from '../theme/colorModeContext';

export function ThemeToggle() {
  const { mode, toggle } = useColorMode();
  const next = mode === 'dark' ? 'light' : 'dark';
  return (
    <IconButton onClick={toggle} aria-label={`Switch to ${next} mode`}>
      {mode === 'dark' ? <LightModeOutlined /> : <DarkModeOutlined />}
    </IconButton>
  );
}
