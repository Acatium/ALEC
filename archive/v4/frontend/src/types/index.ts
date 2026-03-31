/**
 * Re-export API types for convenience
 */

export * from '@/api/types';

/**
 * UI-specific types
 */

export interface NavItem {
  label: string;
  path: string;
  icon?: string;
}

export interface TabItem {
  id: string;
  label: string;
  content?: React.ReactNode;
}

export interface SelectOption<T = string> {
  value: T;
  label: string;
  description?: string;
}

export interface PaginationState {
  page: number;
  pageSize: number;
  total: number;
}

export interface SortState {
  field: string;
  direction: 'asc' | 'desc';
}

export interface FilterState {
  [key: string]: string | number | boolean | undefined;
}
