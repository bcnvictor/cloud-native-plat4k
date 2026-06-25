import React from 'react';
import { cn } from '@/utils/cn';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
  error?: string;
  suffix?: React.ReactNode;
  mono?: boolean;
}

export function Input({
  label,
  hint,
  error,
  suffix,
  mono,
  className,
  id,
  ...props
}: InputProps) {
  const inputId = id ?? label?.toLowerCase().replace(/\s+/g, '-');

  return (
    <div className="flex flex-col gap-1">
      {label && (
        <label htmlFor={inputId} className="text-sm font-medium text-foreground">
          {label}
        </label>
      )}
      <div className="relative flex items-center">
        <input
          id={inputId}
          className={cn(
            'w-full h-8 px-3 text-sm text-foreground rounded-md border border-input bg-background',
            'placeholder:text-muted-foreground',
            'focus:outline-none focus:ring-2 focus:ring-ring',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            error && 'border-danger',
            mono && 'font-mono',
            suffix && 'pr-9',
            className
          )}
          {...props}
        />
        {suffix && (
          <div className="absolute right-2 flex items-center text-muted-foreground">
            {suffix}
          </div>
        )}
      </div>
      {hint && !error && <p className="text-xs text-muted-foreground">{hint}</p>}
      {error && <p className="text-xs text-danger-text">{error}</p>}
    </div>
  );
}
