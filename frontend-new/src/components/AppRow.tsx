import { IconBrandDocker, IconChevronRight } from '@tabler/icons-react';
import { Application } from '@/types';
import { AppHealthStatus } from '@/types';
import { AppStatusBadge } from './AppStatusBadge';
import { timeAgo } from '@/utils/timeAgo';
import { cn } from '@/utils/cn';

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
        'w-full flex items-center gap-3 px-4 py-3 text-left',
        'bg-white rounded-lg border border-zinc-200 hover:border-zinc-300 hover:bg-zinc-50 hover:-translate-y-0.5 hover:shadow-md transition-all duration-150 cursor-pointer',
        isProvisioning && 'opacity-70'
      )}
    >
      <div className="w-8 h-8 rounded-lg bg-zinc-100 flex items-center justify-center shrink-0">
        <IconBrandDocker size={16} className="text-zinc-400" />
      </div>

      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-foreground truncate">{app.name}</p>
        <div className="flex items-center gap-1.5 flex-wrap">
          <p className="text-xs text-muted-foreground">
            {app.origin ?? 'scaffold'} · déployé{' '}
            {timeAgo(app.updated_at ?? app.created_at)}
          </p>
          {app.framework && (
            <span className="font-mono text-xs text-zinc-400 bg-zinc-100 px-1.5 py-0.5 rounded">
              {app.framework}
            </span>
          )}
        </div>
      </div>

      <AppStatusBadge status={healthStatus} />

      <IconChevronRight size={16} className="text-muted-foreground shrink-0" />
    </button>
  );
}
