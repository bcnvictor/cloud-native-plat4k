import { IconAlertTriangle, IconBrandGitlab, IconClock, IconCpu, IconDatabase, IconRefresh, IconServer } from '@tabler/icons-react';
import { useAppDetail } from '@/layouts/AppDetailLayout';
import { MetricCard } from '@/components/MetricCard';
import { Card } from '@/components/ui/Card';
import { Spinner } from '@/components/ui/Spinner';
import { timeAgo } from '@/utils/timeAgo';
import { useAppMetrics } from '@/hooks/useAppMetrics';
import { useAppStatus } from '@/hooks/useAppStatus';
import { useMetricUrl } from '@/hooks/useMonitoringConfig';

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

export function OverviewTab() {
  const { app, isLoading } = useAppDetail();
  const metrics = useAppMetrics(app?.slug ?? '');
  const cpuUrl = useMetricUrl(app?.slug ?? '', 'cpu');
  const ramUrl = useMetricUrl(app?.slug ?? '', 'ram');
  const { data: runtimeStatus } = useAppStatus(app?.id);

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
          value={runtimeStatus?.last_sync_at ? timeAgo(runtimeStatus.last_sync_at) : '—'}
          icon={<IconClock size={14} />}
        />
      </div>

      {/* Status cards */}
      <div className="grid grid-cols-1 gap-4">
        {/* ArgoCD / cluster status */}
        <Card>
          <h2 className="text-sm font-medium text-foreground mb-3">
            <span className="flex items-center gap-1.5">
              <IconRefresh size={14} />
              ArgoCD / cluster
            </span>
          </h2>
          {runtimeStatus?.argocd_error && !runtimeStatus.sync_status ? (
            <p className="text-xs text-muted-foreground flex items-center gap-1.5">
              <IconAlertTriangle size={12} className="shrink-0" />
              ArgoCD unavailable
            </p>
          ) : (
            <dl className="flex flex-col gap-2">
              {[
                {
                  label: 'Sync',
                  value: <SyncBadge status={runtimeStatus?.sync_status} />,
                },
                {
                  label: 'Health',
                  value: <HealthBadge status={runtimeStatus?.health_status} />,
                },
                {
                  label: 'Pods',
                  value: runtimeStatus?.pods_running != null
                    ? `${runtimeStatus.pods_running}/${runtimeStatus.pods_total} running`
                    : '—',
                  mono: true,
                },
                {
                  label: 'Image',
                  value: runtimeStatus?.image
                    ? runtimeStatus.image.split('/').pop() ?? runtimeStatus.image
                    : '—',
                  mono: true,
                },
                {
                  label: 'Last sync',
                  value: runtimeStatus?.last_sync_at ? timeAgo(runtimeStatus.last_sync_at) : '—',
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


      </div>

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
