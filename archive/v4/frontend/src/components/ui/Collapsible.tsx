/**
 * Collapsible section component with smooth animation
 */

import { useState, useRef, useEffect } from 'react';
import type { ReactNode } from 'react';

interface CollapsibleProps {
  /** Header content - always visible */
  header: ReactNode;
  /** Content to show/hide */
  children: ReactNode;
  /** Initial open state */
  defaultOpen?: boolean;
  /** Optional className for container */
  className?: string;
  /** Color theme for the header */
  colorTheme?: 'amber' | 'purple' | 'green' | 'blue' | 'slate' | 'red';
}

const colorStyles = {
  amber: {
    header: 'bg-amber-50 hover:bg-amber-100 dark:bg-amber-900/30 dark:hover:bg-amber-900/50',
    icon: 'text-amber-500',
    border: 'border-amber-200 dark:border-amber-800',
    badge: 'bg-amber-500',
  },
  purple: {
    header: 'bg-purple-50 hover:bg-purple-100 dark:bg-purple-900/30 dark:hover:bg-purple-900/50',
    icon: 'text-purple-500',
    border: 'border-purple-200 dark:border-purple-800',
    badge: 'bg-purple-500',
  },
  green: {
    header: 'bg-green-50 hover:bg-green-100 dark:bg-green-900/30 dark:hover:bg-green-900/50',
    icon: 'text-green-500',
    border: 'border-green-200 dark:border-green-800',
    badge: 'bg-green-500',
  },
  blue: {
    header: 'bg-blue-50 hover:bg-blue-100 dark:bg-blue-900/30 dark:hover:bg-blue-900/50',
    icon: 'text-blue-500',
    border: 'border-blue-200 dark:border-blue-800',
    badge: 'bg-blue-500',
  },
  slate: {
    header: 'bg-slate-50 hover:bg-slate-100 dark:bg-slate-900/30 dark:hover:bg-slate-900/50',
    icon: 'text-slate-500',
    border: 'border-slate-200 dark:border-slate-700',
    badge: 'bg-slate-500',
  },
  red: {
    header: 'bg-red-50 hover:bg-red-100 dark:bg-red-900/30 dark:hover:bg-red-900/50',
    icon: 'text-red-500',
    border: 'border-red-200 dark:border-red-800',
    badge: 'bg-red-500',
  },
};

export function Collapsible({
  header,
  children,
  defaultOpen = false,
  className = '',
  colorTheme = 'slate',
}: CollapsibleProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const contentRef = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState<number | undefined>(defaultOpen ? undefined : 0);

  const colors = colorStyles[colorTheme];

  useEffect(() => {
    if (!contentRef.current) return;

    if (isOpen) {
      const contentHeight = contentRef.current.scrollHeight;
      setHeight(contentHeight);
      // After animation, set to undefined to allow dynamic content
      const timer = setTimeout(() => setHeight(undefined), 300);
      return () => clearTimeout(timer);
    } else {
      // First set to current height, then to 0 for smooth animation
      setHeight(contentRef.current.scrollHeight);
      requestAnimationFrame(() => setHeight(0));
    }
  }, [isOpen]);

  return (
    <div className={`overflow-hidden rounded-xl border ${colors.border} ${className}`}>
      <button
        type="button"
        className={`flex w-full items-center gap-3 p-4 text-left transition-colors ${colors.header}`}
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
      >
        <svg
          className={`h-5 w-5 flex-shrink-0 transition-transform duration-200 ${colors.icon} ${isOpen ? 'rotate-90' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        <div className="flex-1">{header}</div>
      </button>
      <div
        ref={contentRef}
        className="overflow-hidden transition-[height] duration-300 ease-in-out"
        style={{ height: height !== undefined ? `${height}px` : 'auto' }}
      >
        <div className="border-t border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-900">
          {children}
        </div>
      </div>
    </div>
  );
}

interface ServiceHeaderProps {
  icon: string;
  name: string;
  role: string;
  brief: string;
  colorTheme: 'amber' | 'purple' | 'green' | 'blue' | 'slate' | 'red';
}

export function ServiceHeader({ icon, name, role, brief, colorTheme }: ServiceHeaderProps) {
  const colors = colorStyles[colorTheme];

  return (
    <div className="flex items-center gap-3">
      <span
        className={`flex h-10 w-10 items-center justify-center rounded-lg text-base font-bold text-white ${colors.badge}`}
      >
        {icon}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-lg font-semibold text-gray-900 dark:text-gray-100">{name}</span>
          <span className="rounded-full bg-gray-200 px-2 py-0.5 text-xs font-medium text-gray-600 dark:bg-gray-700 dark:text-gray-300">
            {role}
          </span>
        </div>
        <p className="text-sm text-gray-500 dark:text-gray-400 truncate">{brief}</p>
      </div>
    </div>
  );
}

export default Collapsible;
