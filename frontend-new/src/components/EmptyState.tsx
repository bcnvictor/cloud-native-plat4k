import React from 'react';
import { Button } from '@/components/ui/Button';
import { IconInbox } from '@tabler/icons-react';

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
      <div className="text-muted-foreground mb-3">
        {icon ?? <IconInbox size={40} strokeWidth={1.5} />}
      </div>
      <p className="text-sm font-medium text-foreground mb-1">{title}</p>
      {description && <p className="text-sm text-muted-foreground mb-4">{description}</p>}
      {action && (
        <Button variant="primary" size="sm" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
    </div>
  );
}
