/**
 * Utility functions
 */

import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { format, formatDistanceToNow, parseISO } from 'date-fns';

/**
 * Merge Tailwind classes with clsx
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/**
 * Format a date string
 */
export function formatDate(dateString: string | null | undefined): string {
  if (!dateString) return '-';
  try {
    return format(parseISO(dateString), 'MMM d, yyyy HH:mm');
  } catch {
    return dateString;
  }
}

/**
 * Format a date as relative time
 */
export function formatRelativeTime(dateString: string | null | undefined): string {
  if (!dateString) return '-';
  try {
    return formatDistanceToNow(parseISO(dateString), { addSuffix: true });
  } catch {
    return dateString;
  }
}

/**
 * Format a number as percentage
 */
export function formatPercent(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined) return '-';
  return `${(value * 100).toFixed(decimals)}%`;
}

/**
 * Format a number with commas
 */
export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return '-';
  return value.toLocaleString();
}

/**
 * Truncate a string with ellipsis
 */
export function truncate(str: string, length: number): string {
  if (str.length <= length) return str;
  return `${str.slice(0, length)}...`;
}

/**
 * Map polarity to display label
 */
export function polarityToLabel(polarity: string): string {
  switch (polarity) {
    case 'do':
      return 'Solutions';
    case 'dont':
      return 'Constraints';
    case 'know':
      return 'Reference';
    default:
      return polarity;
  }
}

/**
 * Map polarity to color class
 */
export function polarityToColor(polarity: string): string {
  switch (polarity) {
    case 'do':
      return 'text-green-600 bg-green-100 dark:text-green-400 dark:bg-green-900/30';
    case 'dont':
      return 'text-red-600 bg-red-100 dark:text-red-400 dark:bg-red-900/30';
    case 'know':
      return 'text-blue-600 bg-blue-100 dark:text-blue-400 dark:bg-blue-900/30';
    default:
      return 'text-gray-600 bg-gray-100 dark:text-gray-400 dark:bg-gray-800';
  }
}

/**
 * Map micro-outcome to display label
 */
export function microOutcomeToLabel(outcome: string | null): string {
  switch (outcome) {
    case 'progress':
      return 'Progress';
    case 'solved':
      return 'Solved';
    case 'stuck':
      return 'Stuck';
    case 'error':
      return 'Error';
    default:
      return '-';
  }
}

/**
 * Map micro-outcome to color class
 */
export function microOutcomeToColor(outcome: string | null): string {
  switch (outcome) {
    case 'progress':
      return 'text-blue-600 bg-blue-100 dark:text-blue-400 dark:bg-blue-900/30';
    case 'solved':
      return 'text-green-600 bg-green-100 dark:text-green-400 dark:bg-green-900/30';
    case 'stuck':
      return 'text-yellow-600 bg-yellow-100 dark:text-yellow-400 dark:bg-yellow-900/30';
    case 'error':
      return 'text-red-600 bg-red-100 dark:text-red-400 dark:bg-red-900/30';
    default:
      return 'text-gray-600 bg-gray-100 dark:text-gray-400 dark:bg-gray-800';
  }
}

/**
 * Map status to color class
 */
export function statusToColor(status: string): string {
  switch (status) {
    case 'active':
    case 'running':
    case 'healthy':
      return 'text-green-600 bg-green-100 dark:text-green-400 dark:bg-green-900/30';
    case 'completed':
    case 'success':
      return 'text-blue-600 bg-blue-100 dark:text-blue-400 dark:bg-blue-900/30';
    case 'candidate':
    case 'pending':
      return 'text-yellow-600 bg-yellow-100 dark:text-yellow-400 dark:bg-yellow-900/30';
    case 'failed':
    case 'error':
    case 'banned':
      return 'text-red-600 bg-red-100 dark:text-red-400 dark:bg-red-900/30';
    case 'archived':
    case 'stopped':
      return 'text-gray-600 bg-gray-100 dark:text-gray-400 dark:bg-gray-800';
    default:
      return 'text-gray-600 bg-gray-100 dark:text-gray-400 dark:bg-gray-800';
  }
}

/**
 * Calculate effectiveness score
 */
export function calculateEffectiveness(
  helpful: number,
  harmful: number,
  neutral: number
): number {
  const total = helpful + harmful + neutral;
  if (total === 0) return 0;
  return helpful / total;
}

/**
 * Generate a unique ID
 */
export function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

/**
 * Debounce a function
 */
export function debounce<T extends (...args: Parameters<T>) => ReturnType<T>>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: ReturnType<typeof setTimeout> | null = null;

  return (...args: Parameters<T>) => {
    if (timeout) clearTimeout(timeout);
    timeout = setTimeout(() => func(...args), wait);
  };
}
