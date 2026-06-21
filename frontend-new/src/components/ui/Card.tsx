import React from 'react';
import { cn } from '@/utils/cn';

interface CardProps {
  children: React.ReactNode;
  className?: string;
  onClick?: () => void;
  hoverable?: boolean;
  padding?: 'none' | 'sm' | 'md';
}

export function Card({
  children,
  className,
  onClick,
  hoverable,
  padding = 'md',
}: CardProps) {
  return (
    <div
      onClick={onClick}
      className={cn(
        'bg-background border border-border rounded-lg',
        padding === 'sm' && 'p-3',
        padding === 'md' && 'p-4',
        hoverable && 'cursor-pointer transition-shadow hover:shadow-sm',
        onClick && 'cursor-pointer',
        className
      )}
    >
      {children}
    </div>
  );
}
