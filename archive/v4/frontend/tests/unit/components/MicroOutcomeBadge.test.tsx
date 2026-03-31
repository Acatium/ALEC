/**
 * Unit tests for MicroOutcomeBadge component
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MicroOutcomeBadge } from '@/components/session/MicroOutcomeBadge';

describe('MicroOutcomeBadge', () => {
  it('renders progress outcome correctly', () => {
    render(<MicroOutcomeBadge outcome="progress" />);

    expect(screen.getByText('progress')).toBeInTheDocument();
  });

  it('renders solved outcome correctly', () => {
    render(<MicroOutcomeBadge outcome="solved" />);

    expect(screen.getByText('solved')).toBeInTheDocument();
  });

  it('renders stuck outcome correctly', () => {
    render(<MicroOutcomeBadge outcome="stuck" />);

    expect(screen.getByText('stuck')).toBeInTheDocument();
  });

  it('renders error outcome correctly', () => {
    render(<MicroOutcomeBadge outcome="error" />);

    expect(screen.getByText('error')).toBeInTheDocument();
  });

  it('applies correct color classes for progress', () => {
    const { container } = render(<MicroOutcomeBadge outcome="progress" />);

    expect(container.firstChild).toHaveClass('bg-blue-100');
  });

  it('applies correct color classes for solved', () => {
    const { container } = render(<MicroOutcomeBadge outcome="solved" />);

    expect(container.firstChild).toHaveClass('bg-green-100');
  });

  it('applies correct color classes for stuck', () => {
    const { container } = render(<MicroOutcomeBadge outcome="stuck" />);

    expect(container.firstChild).toHaveClass('bg-yellow-100');
  });

  it('applies correct color classes for error', () => {
    const { container } = render(<MicroOutcomeBadge outcome="error" />);

    expect(container.firstChild).toHaveClass('bg-red-100');
  });

  it('accepts custom className', () => {
    const { container } = render(<MicroOutcomeBadge outcome="progress" className="custom-class" />);

    expect(container.firstChild).toHaveClass('custom-class');
  });
});
