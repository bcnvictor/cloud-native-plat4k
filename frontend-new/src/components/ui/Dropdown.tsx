import React, { useRef, useState, useEffect } from 'react';
import { cn } from '@/utils/cn';

export interface DropdownItem {
  key: string;
  label: React.ReactNode;
  icon?: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  divider?: boolean;
  active?: boolean;
}

interface DropdownProps {
  trigger: React.ReactNode;
  items: DropdownItem[];
  align?: 'left' | 'right';
  width?: number;
}

export function Dropdown({ trigger, items, align = 'left', width = 200 }: DropdownProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  return (
    <div ref={ref} className="relative inline-block">
      <div onClick={() => setOpen((v) => !v)}>{trigger}</div>

      {open && (
        <div
          className={cn(
            'absolute z-50 mt-1 bg-background border border-border rounded-md shadow-md py-1',
            align === 'right' ? 'right-0' : 'left-0'
          )}
          style={{ width }}
        >
          {items.map((item) => (
            <React.Fragment key={item.key}>
              {item.divider && <div className="my-1 border-t border-border" />}
              <button
                className={cn(
                  'w-full flex items-center gap-2 px-3 py-1.5 text-sm text-left transition-colors',
                  item.active
                    ? 'text-primary font-medium'
                    : 'text-foreground hover:bg-accent',
                  item.disabled && 'opacity-40 pointer-events-none'
                )}
                onClick={() => {
                  if (!item.disabled) {
                    item.onClick?.();
                    setOpen(false);
                  }
                }}
                disabled={item.disabled}
              >
                {item.icon && (
                  <span className="shrink-0 text-muted-foreground">{item.icon}</span>
                )}
                <span className="flex-1">{item.label}</span>
                {item.active && (
                  <svg
                    width="12"
                    height="12"
                    viewBox="0 0 12 12"
                    fill="currentColor"
                    className="text-primary shrink-0"
                  >
                    <path d="M10 3L5 8.5 2 5.5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
              </button>
            </React.Fragment>
          ))}
        </div>
      )}
    </div>
  );
}
