/**
 * Structured logging for observability
 */

type LogLevel = 'debug' | 'info' | 'warn' | 'error';

interface LogEntry {
  level: LogLevel;
  event: string;
  timestamp: string;
  [key: string]: unknown;
}

function formatEntry(level: LogLevel, event: string, data?: Record<string, unknown>): LogEntry {
  return {
    level,
    event,
    timestamp: new Date().toISOString(),
    ...data,
  };
}

function logToConsole(entry: LogEntry): void {
  const { level, ...rest } = entry;

  // In production, log as JSON for structured logging
  if (import.meta.env.PROD) {
    console[level](JSON.stringify(rest));
    return;
  }

  // In development, log more readable format
  const color = {
    debug: '\x1b[36m', // cyan
    info: '\x1b[32m',  // green
    warn: '\x1b[33m',  // yellow
    error: '\x1b[31m', // red
  }[level];
  const reset = '\x1b[0m';

  console[level](`${color}[${level.toUpperCase()}]${reset} ${entry.event}`, rest);
}

export const logger = {
  debug: (event: string, data?: Record<string, unknown>): void => {
    if (import.meta.env.DEV) {
      logToConsole(formatEntry('debug', event, data));
    }
  },

  info: (event: string, data?: Record<string, unknown>): void => {
    logToConsole(formatEntry('info', event, data));
  },

  warn: (event: string, data?: Record<string, unknown>): void => {
    logToConsole(formatEntry('warn', event, data));
  },

  error: (event: string, error: Error, data?: Record<string, unknown>): void => {
    logToConsole(
      formatEntry('error', event, {
        error_message: error.message,
        error_name: error.name,
        error_stack: import.meta.env.DEV ? error.stack : undefined,
        ...data,
      })
    );
  },
};
