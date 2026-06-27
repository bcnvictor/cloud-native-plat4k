import { IconBrandDocker, IconChevronRight, IconCloud, IconServer } from '@tabler/icons-react';
import { Application } from '@/types';
import { AppHealthStatus } from '@/types';
import { AppStatusBadge } from './AppStatusBadge';
import { timeAgo } from '@/utils/timeAgo';
import { cn } from '@/utils/cn';

interface AppRowProps {
  app: Application;
  healthStatus: AppHealthStatus;
  clusterName?: string;
  onClick: () => void;
}

export function AppRow({ app, healthStatus, clusterName, onClick }: AppRowProps) {
  const isProvisioning = healthStatus === 'provisioning';

  return (
    <button
      onClick={onClick}
      className={cn(
        'w-full flex items-center gap-3 px-4 py-3 text-left',
        'bg-card rounded-lg border border-border hover:border-border hover:bg-accent hover:-translate-y-0.5 hover:shadow-md transition-all duration-150 cursor-pointer',
        isProvisioning && 'opacity-70'
      )}
    >
      <div className="w-8 h-8 rounded-lg bg-muted flex items-center justify-center shrink-0">
        <IconBrandDocker size={16} className="text-muted-foreground" />
      </div>

      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-foreground truncate">{app.name}</p>
        <div className="flex items-center gap-1.5 flex-wrap">
          <p className="text-xs text-muted-foreground">
            {app.origin ?? 'scaffold'} · deployed{' '}
            {timeAgo(app.updated_at ?? app.created_at)}
          </p>
          {app.framework && (
            <span className="font-mono text-xs text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
              {app.framework}
            </span>
          )}
        </div>
      </div>

      {clusterName && (
        <ClusterTag name={clusterName} />
      )}

      <AppStatusBadge status={healthStatus} />

      <IconChevronRight size={16} className="text-muted-foreground shrink-0" />
    </button>
  );
}

function ClusterTag({ name }: { name: string }) {
  const isPrivate = name.toLowerCase().includes('k3s') || name.toLowerCase().includes('oracle') || name.toLowerCase().includes('priv');
  return (
    <span className={cn(
      'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium shrink-0',
      isPrivate
        ? 'bg-purple-500/10 text-purple-400'
        : 'bg-blue-500/10 text-blue-400'
    )}>
      {isPrivate ? <IconServer size={11} /> : <IconCloud size={11} />}
      {name}
    </span>
  );
}
