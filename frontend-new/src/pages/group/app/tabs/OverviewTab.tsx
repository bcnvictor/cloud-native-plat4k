import { IconAlertTriangle, IconBrandGitlab, IconClock, IconCloud, IconCpu, IconDatabase, IconRefresh, IconServer } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { useAppDetail } from '@/layouts/AppDetailLayout';
import { MetricCard } from '@/components/MetricCard';
import { Card } from '@/components/ui/Card';
import { Spinner } from '@/components/ui/Spinner';
import { timeAgo } from '@/utils/timeAgo';
import { useAppMetrics } from '@/hooks/useAppMetrics';
import { useAppStatus } from '@/hooks/useAppStatus';
import { useMetricUrl } from '@/hooks/useMonitoringConfig';
import { clustersApi } from '@/api/clusters';
import { cn } from '@/utils/cn';
import type { ArgoEnvStatus } from '@/types';

function SyncBadge({ status }: { status: string | null | undefined }) {
  if (!status) return <span className="text-xs text-muted-foreground">—</span>;
  const synced = status === 'Synced';
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${synced ? 'bg-success/15 text-success-text' : 'bg-warning/15 text-warning-text'}`}>
      {status}
    </span>
  );
}

function HealthBadge({ status }: { status: string | null | undefined }) {
  if (!status) return <span className="text-xs text-muted-foreground">—</span>;
  const color =
    status === 'Healthy' ? 'bg-success/15 text-success-text' :
    status === 'Degraded' ? 'bg-destructive/15 text-destructive' :
    'bg-warning/15 text-warning-text';
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${color}`}>
      {status}
    </span>
  );
}

function ArgoCard({ title, env }: { title: string; env: ArgoEnvStatus | null | undefined }) {
  return (
    <Card>
      <h2 className="text-sm font-medium text-foreground mb-3">
        <span className="flex items-center gap-1.5">
          <IconRefresh size={14} />
          {title}
        </span>
      </h2>
      {!env || (env.error && !env.sync_status) ? (
        <p className="text-xs text-muted-foreground flex items-center gap-1.5">
          <IconAlertTriangle size={12} className="shrink-0" />
          {env?.error ?? 'Unavailable'}
        </p>
      ) : (
        <dl className="flex flex-col gap-2">
          {[
            { label: 'Sync', value: <SyncBadge status={env.sync_status} /> },
            { label: 'Health', value: <HealthBadge status={env.health_status} /> },
            {
              label: 'Image',
              value: env.image ? env.image.split('/').pop() ?? env.image : '—',
              mono: true,
            },
            {
              label: 'Last sync',
              value: env.last_sync_at ? timeAgo(env.last_sync_at) : '—',
            },
          ].map(({ label, value, mono }) => (
            <div key={label} className="flex items-baseline gap-2">
              <dt className="text-xs text-muted-foreground w-20 shrink-0">{label}</dt>
              <dd className={`text-xs text-foreground ${mono ? 'font-mono' : ''}`}>{value}</dd>
            </div>
          ))}
        </dl>
      )}
    </Card>
  );
}

export function OverviewTab() {
  const { app, isLoading } = useAppDetail();
  const metrics = useAppMetrics(app?.slug ?? '');
  const cpuUrl = useMetricUrl(app?.slug ?? '', 'cpu');
  const ramUrl = useMetricUrl(app?.slug ?? '', 'ram');
  const { data: runtimeStatus } = useAppStatus(app?.id);
  const { data: clusters = [] } = useQuery({ queryKey: ['clusters'], queryFn: clustersApi.list });
  const cluster = app?.target_cluster_id
    ? clusters.find((c) => c.id === app.target_cluster_id)
    : undefined;

  const lastSync =
    runtimeStatus?.argocd_prod?.last_sync_at ??
    runtimeStatus?.argocd_dev?.last_sync_at ??
    null;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      {/* Metrics */}
      <div className="grid grid-cols-4 gap-4">
        {!metrics.available && (
          <div className="col-span-4 flex items-center gap-2 px-3 py-2 rounded-md bg-muted/40 border border-border text-xs text-muted-foreground">
            <IconAlertTriangle size={13} className="shrink-0" />
            Metrics unavailable — check Prometheus connection
          </div>
        )}
        <MetricCard
          label="CPU"
          value={metrics.available ? metrics.cpu.current.toFixed(1) : '—'}
          unit={metrics.available ? 'm' : undefined}
          icon={<IconCpu size={14} />}
          sparkline={metrics.cpu.series}
          externalUrl={cpuUrl ?? undefined}
        />
        <MetricCard
          label="RAM"
          value={metrics.available ? metrics.ram.current.toFixed(0) : '—'}
          unit={metrics.available ? metrics.ramUnit : undefined}
          icon={<IconDatabase size={14} />}
          sparkline={metrics.ram.series}
          externalUrl={ramUrl ?? undefined}
        />
        <MetricCard
          label="Replicas"
          value={
            runtimeStatus?.replicas_ready != null && runtimeStatus?.replicas_desired != null
              ? `${runtimeStatus.replicas_ready}/${runtimeStatus.replicas_desired}`
              : '—'
          }
          icon={<IconServer size={14} />}
        />
        <MetricCard
          label="Last sync"
          value={lastSync ? timeAgo(lastSync) : '—'}
          icon={<IconClock size={14} />}
        />
      </div>

      {/* ArgoCD env cards */}
      {runtimeStatus?.argocd_error && !runtimeStatus.argocd_prod && !runtimeStatus.argocd_dev ? (
        <Card>
          <p className="text-xs text-muted-foreground flex items-center gap-1.5">
            <IconAlertTriangle size={12} className="shrink-0" />
            ArgoCD unavailable — {runtimeStatus.argocd_error}
          </p>
        </Card>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          <ArgoCard title="Production environment" env={runtimeStatus?.argocd_prod} />
          <ArgoCard title="Dev environment" env={runtimeStatus?.argocd_dev} />
        </div>
      )}

      {/* Cloud target */}
      {cluster && (
        <Card>
          <h2 className="text-sm font-medium text-foreground mb-3">Cloud target</h2>
          <div className="flex items-center gap-2">
            {cluster.name.toLowerCase().includes('k3s') || cluster.name.toLowerCase().includes('oracle') || cluster.name.toLowerCase().includes('priv') ? (
              <IconServer size={14} className="text-purple-400 shrink-0" />
            ) : (
              <IconCloud size={14} className="text-blue-400 shrink-0" />
            )}
            <span className={cn(
              'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium',
              cluster.name.toLowerCase().includes('k3s') || cluster.name.toLowerCase().includes('oracle') || cluster.name.toLowerCase().includes('priv')
                ? 'bg-purple-500/10 text-purple-400'
                : 'bg-blue-500/10 text-blue-400'
            )}>
              {cluster.name}
            </span>
            <span className="text-xs text-muted-foreground">{cluster.endpoint}</span>
            <span className={cn(
              'ml-auto text-xs px-2 py-0.5 rounded-full',
              cluster.status === 'online' ? 'bg-success/15 text-success-text' : 'bg-muted text-muted-foreground'
            )}>
              {cluster.status}
            </span>
          </div>
        </Card>
      )}

      {/* Quick access */}
      <Card>
        <h2 className="text-sm font-medium text-foreground mb-3">Quick access</h2>
        {(app?.repo_url ?? app?.source_url) ? (
          <a
            href={(app!.repo_url ?? app!.source_url)!}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 text-sm text-[#007BA7] hover:underline"
          >
            <IconBrandGitlab size={16} />
            {app!.repo_url ?? app!.source_url}
          </a>
        ) : (
          <span className="flex items-center gap-2 text-sm text-muted-foreground">
            <IconBrandGitlab size={16} />
            GitLab not configured
          </span>
        )}
      </Card>
    </div>
  );
}
