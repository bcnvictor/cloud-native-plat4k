import { IconBrandDocker, IconChevronRight } from '@tabler/icons-react';
import { Application } from '@/types';
import { AppHealthStatus } from '@/types';
import { AppStatusBadge } from './AppStatusBadge';
import { timeAgo } from '@/utils/timeAgo';
import { cn } from '@/lib/cn';

interface AppRowProps {
  app: Application;
  healthStatus: AppHealthStatus;
  onClick: () => void;
}

export function AppRow({ app, healthStatus, onClick }: AppRowProps) {
  const isProvisioning = healthStatus === 'provisioning';

  return (
    <button
      onClick={onClick}
      className={cn(
        'w-full flex items-center gap-3 px-4 py-4 text-left transition-colors',
        'border-b border-border last:border-0 hover:bg-accent',
        isProvisioning && 'opacity-70'
      )}
    >
      <div className="w-8 h-8 rounded-lg bg-zinc-100 flex items-center justify-center shrink-0">
        <IconBrandDocker size={16} className="text-zinc-400" />
      </div>

      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-foreground truncate">{app.name}</p>
        <p className="text-xs text-muted-foreground">
          {app.origin ?? 'scaffold'} · déployé{' '}
          {timeAgo(app.updated_at ?? app.created_at)}
        </p>
      </div>

      <AppStatusBadge status={healthStatus} />

      <IconChevronRight size={16} className="text-muted-foreground shrink-0" />
    </button>
  );
}
