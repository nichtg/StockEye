import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';
import { tokenStore } from '../api/tokens';

afterEach(() => {
  cleanup();
  localStorage.clear();
  tokenStore.clear();
});
