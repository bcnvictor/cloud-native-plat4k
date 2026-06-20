import React from 'react';
import { cn } from '@/lib/cn';

interface BadgeProps {
  variant?: 'success' | 'warning' | 'danger' | 'info' | 'muted' | 'primary';
  children: React.ReactNode;
  className?: string;
}

const VARIANTS = {
  success: 'bg-success-subtle text-success-text',
  warning: 'bg-warning-subtle text-warning-text',
  danger: 'bg-danger-subtle text-danger-text',
  info: 'bg-info-subtle text-info-text',
  muted: 'bg-muted text-muted-foreground',
  primary: 'bg-primary-subtle text-primary',
};

export function Badge({ variant = 'muted', children, className }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
        VARIANTS[variant],
        className
      )}
    >
      {children}
    </span>
  );
}
