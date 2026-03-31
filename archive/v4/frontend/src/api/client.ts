/**
 * API Client - Base fetch wrapper with error handling and logging
 */

import { logger } from '@/observability/logger';
import type { APIErrorData } from './types';

// ============================================================================
// Constants
// ============================================================================

const API_BASE = '/api/v1';
const DEFAULT_TIMEOUT = 30000; // 30s

// ============================================================================
// Error Class
// ============================================================================

export class ApiError extends Error {
  status: number;
  statusText: string;
  code?: string;
  details?: APIErrorData;

  constructor(
    status: number,
    statusText: string,
    message: string,
    code?: string,
    details?: APIErrorData
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.statusText = statusText;
    this.code = code;
    this.details = details;
  }

  static fromResponse(status: number, statusText: string, data: APIErrorData): ApiError {
    const message = data.detail || data.message || `Request failed with status ${status}`;
    return new ApiError(status, statusText, message, undefined, data);
  }
}

// ============================================================================
// Request Options
// ============================================================================

export interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  timeout?: number;
  skipLog?: boolean;
}

// ============================================================================
// Core Request Function
// ============================================================================

export async function apiRequest<T>(
  endpoint: string,
  options: RequestOptions = {}
): Promise<T> {
  const { body, timeout = DEFAULT_TIMEOUT, skipLog = false, ...fetchOptions } = options;

  const url = endpoint.startsWith('/') ? `${API_BASE}${endpoint}` : `${API_BASE}/${endpoint}`;
  const startTime = performance.now();

  // Set up abort controller for timeout
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    // Build headers with CSRF protection for state-changing requests
    const method = (fetchOptions.method || 'GET').toUpperCase();
    const isStateChanging = ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method);
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...(isStateChanging && { 'X-Requested-With': 'XMLHttpRequest' }),
      ...fetchOptions.headers,
    };

    const response = await fetch(url, {
      ...fetchOptions,
      signal: controller.signal,
      credentials: 'same-origin', // Only send cookies to same origin
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });

    clearTimeout(timeoutId);
    const duration = performance.now() - startTime;

    // Log request (unless skipped)
    if (!skipLog) {
      logger.info('api_request', {
        endpoint,
        method: fetchOptions.method || 'GET',
        status: response.status,
        duration_ms: Math.round(duration),
      });
    }

    // Handle non-OK responses
    if (!response.ok) {
      let errorData: APIErrorData = {};
      try {
        errorData = await response.json();
      } catch {
        // Response body wasn't JSON
      }

      const error = ApiError.fromResponse(response.status, response.statusText, errorData);
      logger.error('api_error', error, {
        endpoint,
        status: response.status,
      });
      throw error;
    }

    // Handle 204 No Content
    if (response.status === 204) {
      return undefined as T;
    }

    // Parse JSON response
    const data = await response.json();
    return data as T;
  } catch (error) {
    clearTimeout(timeoutId);

    // Handle abort/timeout
    if (error instanceof DOMException && error.name === 'AbortError') {
      const timeoutError = new ApiError(408, 'Request Timeout', `Request timeout after ${timeout}ms`, 'TIMEOUT');
      logger.error('api_timeout', timeoutError, { endpoint, timeout });
      throw timeoutError;
    }

    // Re-throw ApiErrors
    if (error instanceof ApiError) {
      throw error;
    }

    // Handle network errors
    const networkError = new ApiError(
      0,
      'Network Error',
      error instanceof Error ? error.message : 'Network error',
      'NETWORK_ERROR'
    );
    logger.error('api_network_error', networkError, { endpoint });
    throw networkError;
  }
}

// ============================================================================
// Convenience Methods
// ============================================================================

export const api = {
  get: <T>(endpoint: string, options?: RequestOptions) =>
    apiRequest<T>(endpoint, { ...options, method: 'GET' }),

  post: <T>(endpoint: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(endpoint, { ...options, method: 'POST', body }),

  patch: <T>(endpoint: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(endpoint, { ...options, method: 'PATCH', body }),

  put: <T>(endpoint: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(endpoint, { ...options, method: 'PUT', body }),

  delete: <T>(endpoint: string, options?: RequestOptions) =>
    apiRequest<T>(endpoint, { ...options, method: 'DELETE' }),
};

// ============================================================================
// Query String Builder
// ============================================================================

export function buildQueryString(params: Record<string, unknown>): string {
  const searchParams = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      searchParams.append(key, String(value));
    }
  }

  const queryString = searchParams.toString();
  return queryString ? `?${queryString}` : '';
}

// ============================================================================
// Legacy exports for test compatibility
// ============================================================================

export const apiClient = {
  get: <T>(endpoint: string, params?: Record<string, unknown>) => {
    const qs = params ? buildQueryString(params) : '';
    return api.get<T>(`${endpoint}${qs}`);
  },
  post: api.post,
  patch: api.patch,
  put: api.put,
  delete: api.delete,
};
