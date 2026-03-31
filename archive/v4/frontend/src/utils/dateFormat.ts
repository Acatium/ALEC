/**
 * Date formatting utilities for displaying UTC timestamps in local time.
 */

/**
 * Format a UTC timestamp string to local time.
 * Handles timestamps with or without 'Z' suffix.
 */
export function formatLocalTime(timestamp: string): string {
  if (!timestamp) return '';

  // Ensure the timestamp is treated as UTC
  let utcTimestamp = timestamp;
  if (!timestamp.endsWith('Z') && !timestamp.includes('+') && !timestamp.includes('-', 10)) {
    utcTimestamp = timestamp + 'Z';
  }

  const date = new Date(utcTimestamp);

  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

/**
 * Format a UTC timestamp to local date only.
 */
export function formatLocalDate(timestamp: string): string {
  if (!timestamp) return '';

  let utcTimestamp = timestamp;
  if (!timestamp.endsWith('Z') && !timestamp.includes('+') && !timestamp.includes('-', 10)) {
    utcTimestamp = timestamp + 'Z';
  }

  const date = new Date(utcTimestamp);

  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

/**
 * Format a UTC timestamp as relative time (e.g., "5 minutes ago").
 */
export function formatTimeAgo(timestamp: string): string {
  if (!timestamp) return '';

  let utcTimestamp = timestamp;
  if (!timestamp.endsWith('Z') && !timestamp.includes('+') && !timestamp.includes('-', 10)) {
    utcTimestamp = timestamp + 'Z';
  }

  const date = new Date(utcTimestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;

  return formatLocalDate(timestamp);
}

/**
 * Format a UTC timestamp with full details including timezone.
 */
export function formatLocalTimeFull(timestamp: string): string {
  if (!timestamp) return '';

  let utcTimestamp = timestamp;
  if (!timestamp.endsWith('Z') && !timestamp.includes('+') && !timestamp.includes('-', 10)) {
    utcTimestamp = timestamp + 'Z';
  }

  const date = new Date(utcTimestamp);

  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
    timeZoneName: 'short',
  });
}
