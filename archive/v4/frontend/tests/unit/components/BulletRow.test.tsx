/**
 * Unit tests for BulletRow component
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { BulletRow } from '@/components/library/BulletRow';
import type { BulletResponse } from '@/api/types';

const mockBullet: BulletResponse = {
  id: 'bullet-123',
  situation: 'When testing React components',
  assertion: 'Use React Testing Library',
  modality: 'should',
  polarity: 'do',
  domain: 'testing',
  helpful_count: 10,
  harmful_count: 2,
  neutral_count: 5,
  status: 'active',
  created_at: '2025-01-01T00:00:00Z',
};

function renderWithRouter(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>);
}

describe('BulletRow', () => {
  it('renders bullet situation', () => {
    renderWithRouter(<BulletRow bullet={mockBullet} selected={false} onSelect={vi.fn()} />);

    expect(screen.getByText('When testing React components')).toBeInTheDocument();
  });

  it('renders bullet assertion', () => {
    renderWithRouter(<BulletRow bullet={mockBullet} selected={false} onSelect={vi.fn()} />);

    expect(screen.getByText('Use React Testing Library')).toBeInTheDocument();
  });

  it('renders polarity badge', () => {
    renderWithRouter(<BulletRow bullet={mockBullet} selected={false} onSelect={vi.fn()} />);

    // The PolarityBadge should show "Solutions" for polarity="do"
    expect(screen.getByText('Solutions')).toBeInTheDocument();
  });

  it('renders status badge', () => {
    renderWithRouter(<BulletRow bullet={mockBullet} selected={false} onSelect={vi.fn()} />);

    expect(screen.getByText('active')).toBeInTheDocument();
  });

  it('displays effectiveness percentage', () => {
    renderWithRouter(<BulletRow bullet={mockBullet} selected={false} onSelect={vi.fn()} />);

    // effectiveness = helpful / (helpful + harmful + neutral) = 10 / 17 ≈ 59%
    expect(screen.getByText(/59/)).toBeInTheDocument();
  });

  it('calls onSelect when checkbox is clicked', () => {
    const onSelect = vi.fn();
    renderWithRouter(<BulletRow bullet={mockBullet} selected={false} onSelect={onSelect} />);

    const checkbox = screen.getByRole('checkbox');
    fireEvent.click(checkbox);

    expect(onSelect).toHaveBeenCalledWith('bullet-123');
  });

  it('shows checkbox as checked when selected', () => {
    renderWithRouter(<BulletRow bullet={mockBullet} selected={true} onSelect={vi.fn()} />);

    const checkbox = screen.getByRole('checkbox');
    expect(checkbox).toBeChecked();
  });

  it('shows checkbox as unchecked when not selected', () => {
    renderWithRouter(<BulletRow bullet={mockBullet} selected={false} onSelect={vi.fn()} />);

    const checkbox = screen.getByRole('checkbox');
    expect(checkbox).not.toBeChecked();
  });

  it('links to bullet detail page', () => {
    renderWithRouter(<BulletRow bullet={mockBullet} selected={false} onSelect={vi.fn()} />);

    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', '/bullets/bullet-123');
  });

  it('handles different polarities', () => {
    const dontBullet = { ...mockBullet, polarity: 'dont' as const };
    renderWithRouter(<BulletRow bullet={dontBullet} selected={false} onSelect={vi.fn()} />);

    expect(screen.getByText('Constraints')).toBeInTheDocument();
  });

  it('handles know polarity', () => {
    const knowBullet = { ...mockBullet, polarity: 'know' as const };
    renderWithRouter(<BulletRow bullet={knowBullet} selected={false} onSelect={vi.fn()} />);

    expect(screen.getByText('Reference')).toBeInTheDocument();
  });
});
