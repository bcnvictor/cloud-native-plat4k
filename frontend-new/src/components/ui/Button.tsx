import React from 'react';
import { cn } from '@/lib/cn';
import { IconLoader2 } from '@tabler/icons-react';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md';
  loading?: boolean;
  icon?: React.ReactNode;
}

const VARIANTS = {
  primary: 'bg-primary text-primary-foreground hover:bg-primary-hover active:bg-primary-active',
  secondary: 'bg-secondary text-foreground border border-border hover:bg-accent',
  ghost: 'text-foreground hover:bg-accent',
  danger: 'bg-danger text-white hover:opacity-90',
};

const SIZES = {
  sm: 'h-7 px-2.5 text-xs rounded-md gap-1',
  md: 'h-8 px-3 text-sm rounded-md gap-1.5',
};

export function Button({
  variant = 'secondary',
  size = 'md',
  loading,
  icon,
  children,
  className,
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center font-medium transition-colors',
        'disabled:opacity-50 disabled:pointer-events-none',
        VARIANTS[variant],
        SIZES[size],
        className
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? (
        <IconLoader2 size={14} className="animate-spin shrink-0" />
      ) : icon ? (
        <span className="shrink-0">{icon}</span>
      ) : null}
      {children}
    </button>
  );
}
