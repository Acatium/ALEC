/**
 * Toggle/Switch component
 */

import { forwardRef, type ChangeEvent } from 'react';
import { cn } from '@/lib/utils';

export interface ToggleProps {
  checked?: boolean;
  onChange?: (checked: boolean) => void;
  label?: string;
  disabled?: boolean;
  className?: string;
  id?: string;
}

const Toggle = forwardRef<HTMLInputElement, ToggleProps>(
  ({ className, label, id, checked, onChange, disabled, ...props }, ref) => {
    const toggleId = id || `toggle-${Math.random().toString(36).slice(2, 9)}`;

    const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
      onChange?.(e.target.checked);
    };

    return (
      <div className={cn('flex items-center', className)}>
        <label htmlFor={toggleId} className="relative inline-flex cursor-pointer items-center">
          <input
            type="checkbox"
            id={toggleId}
            ref={ref}
            className="peer sr-only"
            checked={checked}
            onChange={handleChange}
            disabled={disabled}
            {...props}
          />
          <div
            className={cn(
              'h-6 w-11 rounded-full bg-gray-200 peer-focus:ring-2 peer-focus:ring-blue-500 peer-focus:ring-offset-2',
              'after:absolute after:left-[2px] after:top-[2px] after:h-5 after:w-5 after:rounded-full after:border after:border-gray-300 after:bg-white after:transition-all after:content-[""]',
              'peer-checked:bg-blue-600 peer-checked:after:translate-x-full peer-checked:after:border-white',
              'dark:bg-gray-700 dark:peer-checked:bg-blue-500',
              disabled && 'cursor-not-allowed opacity-50'
            )}
          />
          {label && (
            <span className="ml-3 text-sm font-medium text-gray-900 dark:text-gray-300">
              {label}
            </span>
          )}
        </label>
      </div>
    );
  }
);

Toggle.displayName = 'Toggle';

export { Toggle };
