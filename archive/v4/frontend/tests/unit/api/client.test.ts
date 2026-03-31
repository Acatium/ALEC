/**
 * Unit tests for API client
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient, ApiError } from '@/api/client';

describe('apiClient', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  describe('get', () => {
    it('makes GET request with correct URL', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ data: 'test' }),
      });

      await apiClient.get('/test');

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/test'),
        expect.objectContaining({ method: 'GET' })
      );
    });

    it('adds query params to URL', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({}),
      });

      await apiClient.get('/test', { foo: 'bar', baz: 123 });

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('foo=bar'),
        expect.anything()
      );
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('baz=123'),
        expect.anything()
      );
    });

    it('throws ApiError on non-ok response', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        json: () => Promise.resolve({ detail: 'Resource not found' }),
      });

      await expect(apiClient.get('/test')).rejects.toThrow(ApiError);
    });
  });

  describe('post', () => {
    it('makes POST request with JSON body', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ id: '123' }),
      });

      await apiClient.post('/test', { name: 'test' });

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/test'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ name: 'test' }),
        })
      );
    });

    it('includes Content-Type header', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({}),
      });

      await apiClient.post('/test', {});

      expect(fetch).toHaveBeenCalledWith(
        expect.anything(),
        expect.objectContaining({
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
        })
      );
    });
  });

  describe('patch', () => {
    it('makes PATCH request', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({}),
      });

      await apiClient.patch('/test/123', { name: 'updated' });

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/test/123'),
        expect.objectContaining({ method: 'PATCH' })
      );
    });
  });

  describe('delete', () => {
    it('makes DELETE request', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({}),
      });

      await apiClient.delete('/test/123');

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/test/123'),
        expect.objectContaining({ method: 'DELETE' })
      );
    });
  });
});

describe('ApiError', () => {
  it('contains status and message', () => {
    const error = new ApiError(404, 'Not Found', 'Resource not found');

    expect(error.status).toBe(404);
    expect(error.statusText).toBe('Not Found');
    expect(error.message).toBe('Resource not found');
  });

  it('extends Error', () => {
    const error = new ApiError(500, 'Server Error', 'Something went wrong');

    expect(error).toBeInstanceOf(Error);
  });
});
