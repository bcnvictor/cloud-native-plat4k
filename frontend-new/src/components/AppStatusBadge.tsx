import { cn } from '@/lib/cn';
import { AppHealthStatus } from '@/types';
import { STATUS_LABEL, STATUS_COLOR, STATUS_DOT } from '@/utils/appHealth';
import { IconLoader2 } from '@tabler/icons-react';

interface AppStatusBadgeProps {
  status: AppHealthStatus;
  showDot?: boolean;
  size?: 'sm' | 'md';
}

export function AppStatusBadge({
  status,
  showDot = true,
  size = 'sm',
}: AppStatusBadgeProps) {
  const isAnimated = status === 'deploying' || status === 'updating' || status === 'provisioning';

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full font-medium',
        size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-sm',
        STATUS_COLOR[status]
      )}
    >
      {showDot && (
        isAnimated ? (
          <IconLoader2 size={10} className="animate-spin shrink-0" />
        ) : (
          <span className={cn('h-1.5 w-1.5 rounded-full shrink-0', STATUS_DOT[status])} />
        )
      )}
      {STATUS_LABEL[status]}
    </span>
  );
}
