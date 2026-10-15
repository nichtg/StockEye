import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../test/render';
import LandingPage from './LandingPage';

describe('LandingPage', () => {
  it('has one h1 and an ordered outline of h2 sections', () => {
    renderApp(<LandingPage />);
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual([
      'The week ahead, in one line',
      'What the news really did',
      'Find stocks people overlook',
      'Start with one stock',
    ]);
  });

  it('links the calls to action to register and login', () => {
    renderApp(<LandingPage />);
    for (const link of screen.getAllByRole('link', { name: 'Create a free account' })) {
      expect(link).toHaveAttribute('href', '/register');
    }
    for (const link of screen.getAllByRole('link', { name: 'Sign in' })) {
      expect(link).toHaveAttribute('href', '/login');
    }
  });

  it('gives every screenshot alt text and a size', () => {
    renderApp(<LandingPage />);
    const images = screen.getAllByRole('img');
    expect(images).toHaveLength(3);
    for (const img of images) {
      expect(img.getAttribute('alt')).toBeTruthy();
      expect(img).toHaveAttribute('width');
      expect(img).toHaveAttribute('height');
    }
  });
});
