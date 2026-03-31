/**
 * Unit tests for useBullets hook
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useBullets, useBullet } from '@/hooks/queries/useBullets';
import * as libraryApi from '@/api/library';
import type { ReactNode } from 'react';

vi.mock('@/api/library');

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
});

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
);

describe('useBullets', () => {
  beforeEach(() => {
    queryClient.clear();
    vi.resetAllMocks();
  });

  it('fetches bullets with default parameters', async () => {
    const mockResponse = {
      bullets: [
        {
          id: '1',
          situation: 'Test situation',
          assertion: 'Test assertion',
          modality: 'should',
          polarity: 'do',
          helpful_count: 5,
          harmful_count: 1,
          neutral_count: 2,
          status: 'active',
          created_at: '2025-01-01T00:00:00Z',
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    };

    vi.mocked(libraryApi.getBullets).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useBullets(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual(mockResponse);
    expect(libraryApi.getBullets).toHaveBeenCalledWith({
      page: 1,
      page_size: 20,
    });
  });

  it('passes filter parameters to API', async () => {
    vi.mocked(libraryApi.getBullets).mockResolvedValue({
      bullets: [],
      total: 0,
      page: 1,
      page_size: 10,
    });

    const { result } = renderHook(
      () =>
        useBullets({
          page: 2,
          page_size: 10,
          status: 'active',
          category: 'solutions',
          search: 'test',
        }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(libraryApi.getBullets).toHaveBeenCalledWith({
      page: 2,
      page_size: 10,
      status: 'active',
      category: 'solutions',
      search: 'test',
    });
  });

  it('handles API errors', async () => {
    vi.mocked(libraryApi.getBullets).mockRejectedValue(new Error('API Error'));

    const { result } = renderHook(() => useBullets(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(result.current.error?.message).toBe('API Error');
  });
});

describe('useBullet', () => {
  beforeEach(() => {
    queryClient.clear();
    vi.resetAllMocks();
  });

  it('fetches single bullet by ID', async () => {
    const mockBullet = {
      id: 'bullet-123',
      situation: 'Test situation',
      assertion: 'Test assertion',
      modality: 'should' as const,
      polarity: 'do' as const,
      helpful_count: 5,
      harmful_count: 1,
      neutral_count: 2,
      status: 'active' as const,
      created_at: '2025-01-01T00:00:00Z',
    };

    vi.mocked(libraryApi.getBullet).mockResolvedValue(mockBullet);

    const { result } = renderHook(() => useBullet('bullet-123'), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual(mockBullet);
    expect(libraryApi.getBullet).toHaveBeenCalledWith('bullet-123');
  });

  it('does not fetch when bulletId is undefined', () => {
    const { result } = renderHook(() => useBullet(undefined), { wrapper });

    expect(result.current.isLoading).toBe(false);
    expect(libraryApi.getBullet).not.toHaveBeenCalled();
  });
});
