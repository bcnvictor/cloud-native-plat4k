import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { IconServer2, IconExternalLink, IconWifiOff } from '@tabler/icons-react';
import { useScopeStore } from '@/store/scope';
import { useBreadcrumb } from '@/components/nav/BreadcrumbContext';
import { clustersApi } from '@/api/clusters';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import { timeAgo } from '@/utils/timeAgo';
import type { ClusterConnection } from '@/types';

const STATUS_BADGE: Record<ClusterConnection['status'], {
  variant: 'success' | 'danger' | 'muted';
  label: string;
  pulse: boolean;
  border: string;
  dot: string;
}> = {
  online:  { variant: 'success', label: 'Online',  pulse: true,  border: 'border-success-border', dot: 'bg-success' },
  offline: { variant: 'danger',  label: 'Offline', pulse: false, border: 'border-danger-border',  dot: 'bg-danger' },
  unknown: { variant: 'muted',   label: 'Unknown', pulse: false, border: 'border-border',          dot: 'bg-zinc-400' },
};

function StatusBadge({ status }: { status: ClusterConnection['status'] }) {
  const s = STATUS_BADGE[status] ?? STATUS_BADGE.unknown;
  return (
    <Badge variant={s.variant} className={`border ${s.border} gap-1.5`}>
      <span className="relative flex h-1.5 w-1.5 shrink-0">
        {s.pulse && (
          <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${s.dot} opacity-60`} />
        )}
        <span className={`relative inline-flex h-1.5 w-1.5 rounded-full ${s.dot}`} />
      </span>
      {s.label}
    </Badge>
  );
}

const MONITORING_LINKS: Array<{ key: keyof ClusterConnection; label: string }> = [
  { key: 'prometheus_url', label: 'Prometheus' },
  { key: 'loki_url', label: 'Loki' },
  { key: 'argocd_url', label: 'ArgoCD' },
];

export function Clusters() {
  const { setScope } = useScopeStore();
  const { setBreadcrumb } = useBreadcrumb();
  useEffect(() => { setScope('admin'); }, [setScope]);

  useEffect(() => {
    setBreadcrumb([{ label: 'Platform' }, { label: 'Clusters' }]);
    return () => setBreadcrumb([]);
  }, [setBreadcrumb]);

  const { data: clusters = [], isLoading } = useQuery({
    queryKey: ['clusters'],
    queryFn: clustersApi.list,
  });

  return (
    <div className="max-w-[1440px] mx-auto px-8 py-6">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-foreground">Clusters</h1>
        <p className="text-sm text-muted-foreground">{clusters.length} cluster{clusters.length !== 1 ? 's' : ''}</p>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16"><Spinner size="lg" /></div>
      ) : clusters.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-2 py-16 text-center">
          <IconWifiOff size={24} className="text-zinc-300" />
          <p className="text-sm text-muted-foreground">No cluster registered yet</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          {clusters.map((cluster) => (
            <Card key={cluster.id} padding="none">
              {/* Header */}
              <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
                <div className="h-8 w-8 flex items-center justify-center rounded-md bg-background-subtle border border-border">
                  <IconServer2 size={16} className="text-muted-foreground" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium font-mono text-foreground">{cluster.name}</p>
                  <p className="text-xs text-muted-foreground truncate">{cluster.endpoint}</p>
                </div>
                <StatusBadge status={cluster.status} />
              </div>

              {/* Info */}
              <div className="px-4 py-2.5 border-b border-border flex items-center gap-4 text-xs text-muted-foreground">
                <span>
                  Last seen{' '}
                  <span className="text-foreground">
                    {cluster.last_seen_at ? timeAgo(cluster.last_seen_at) : 'never'}
                  </span>
                </span>
                <span>
                  Registered{' '}
                  <span className="text-foreground">{timeAgo(cluster.created_at)}</span>
                </span>
              </div>

              {/* Monitoring links */}
              <div className="px-4 py-3">
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-2">Monitoring</p>
                <div className="flex flex-wrap gap-3">
                  {MONITORING_LINKS.map(({ key, label }) => {
                    const url = cluster[key] as string | null | undefined;
                    if (!url) return null;
                    return (
                      <a
                        key={key}
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
                      >
                        <IconExternalLink size={13} />
                        {label}
                      </a>
                    );
                  })}
                  {MONITORING_LINKS.every(({ key }) => !cluster[key]) && (
                    <span className="text-xs text-muted-foreground">Not configured</span>
                  )}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
