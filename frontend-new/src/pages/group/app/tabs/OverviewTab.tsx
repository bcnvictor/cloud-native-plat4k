import { useState } from 'react';
import { IconAlertTriangle, IconBrandGitlab, IconClock, IconCloud, IconCpu, IconDatabase, IconExternalLink, IconPlayerPlay, IconPlayerStop, IconRefresh, IconServer, IconTerminal2 } from '@tabler/icons-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAppDetail } from '@/layouts/AppDetailLayout';
import { MetricCard } from '@/components/MetricCard';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
import { toast } from '@/components/ui/toast';
import { timeAgo } from '@/utils/timeAgo';
import { appsApi } from '@/api/apps';
import { useAppMetrics } from '@/hooks/useAppMetrics';
import { useAppStatus } from '@/hooks/useAppStatus';
import { useAppScaleState } from '@/hooks/useAppScaleState';
import { useMetricUrl } from '@/hooks/useMonitoringConfig';
import { appUrl } from '@/utils/appUrls';
import { clustersApi } from '@/api/clusters';
import { isPrivateCluster } from '@/utils/clusterUtils';
import { cn } from '@/utils/cn';
import type { ArgoEnvStatus, AppScaleStateItem } from '@/types';

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
    status === 'Stopped' ? 'bg-muted text-muted-foreground' :
    status === 'Healthy' ? 'bg-success/15 text-success-text' :
    status === 'Degraded' ? 'bg-destructive/15 text-destructive' :
    'bg-warning/15 text-warning-text';
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${color}`}>
      {status}
    </span>
  );
}

interface EnvCardProps {
  title: string;
  envKey: 'dev' | 'prod';
  appId: number;
  argo: ArgoEnvStatus | null | undefined;
  scaleState: AppScaleStateItem | null | undefined;
}

function EnvCard({ title, envKey, appId, argo, scaleState }: EnvCardProps) {
  const [confirming, setConfirming] = useState(false);
  const queryClient = useQueryClient();
  const isStopped = scaleState?.is_stopped ?? false;

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['app-scale-state', appId] });
    queryClient.invalidateQueries({ queryKey: ['app-status', appId] });
  };

  const { mutate: doStop, isPending: stopping } = useMutation({
    mutationFn: () => appsApi.stopApp(appId, envKey),
    onSuccess: () => {
      toast({ title: `${title} stopped`, description: 'Scaled to zero via a gitops commit.' });
      setConfirming(false);
      invalidate();
    },
    onError: (err: Error) => {
      toast({ title: 'Stop failed', description: err.message, variant: 'destructive' });
      setConfirming(false);
    },
  });

  const { mutate: doResume, isPending: resuming } = useMutation({
    mutationFn: () => appsApi.resumeApp(appId, envKey),
    onSuccess: () => {
      toast({ title: `${title} resumed` });
      invalidate();
    },
    onError: (err: Error) => {
      toast({ title: 'Resume failed', description: err.message, variant: 'destructive' });
    },
  });

  const scaleStatusText = isStopped
    ? `Stopped${scaleState?.stop_reason ? ` (${scaleState.stop_reason})` : ''}${scaleState?.stopped_at ? ` · ${timeAgo(scaleState.stopped_at)}` : ''}`
    : 'Running';

  return (
    <Card>
      <h2 className="text-sm font-medium text-foreground mb-3">
        <span className="flex items-center gap-1.5">
          <IconRefresh size={14} />
          {title}
        </span>
      </h2>
      {!argo || (argo.error && !argo.sync_status) ? (
        <p className="text-xs text-muted-foreground flex items-center gap-1.5 mb-3">
          <IconAlertTriangle size={12} className="shrink-0" />
          {argo?.error ?? 'Unavailable'}
        </p>
      ) : (
        <dl className="flex flex-col gap-2 mb-3">
          {[
            { label: 'Sync', value: <SyncBadge status={argo.sync_status} /> },
            { label: 'Health', value: <HealthBadge status={isStopped ? 'Stopped' : argo.health_status} /> },
            {
              label: 'Image',
              value: argo.image ? argo.image.split('/').pop() ?? argo.image : '—',
              mono: true,
            },
            {
              label: 'Last sync',
              value: argo.last_sync_at ? timeAgo(argo.last_sync_at) : '—',
            },
          ].map(({ label, value, mono }) => (
            <div key={label} className="flex items-baseline gap-2">
              <dt className="text-xs text-muted-foreground w-20 shrink-0">{label}</dt>
              <dd className={`text-xs text-foreground ${mono ? 'font-mono' : ''}`}>{value}</dd>
            </div>
          ))}
        </dl>
      )}

      <div className="flex items-center gap-2 pt-3 border-t border-border">
        <span className="flex-1 text-xs text-muted-foreground">{scaleStatusText}</span>
        {isStopped ? (
          <Button size="sm" variant="secondary" icon={<IconPlayerPlay size={13} />} onClick={() => doResume()} disabled={resuming}>
            {resuming ? <Spinner size="sm" /> : 'Resume'}
          </Button>
        ) : confirming ? (
          <div className="flex gap-1.5">
            <Button size="sm" variant="danger" onClick={() => doStop()} disabled={stopping}>
              {stopping ? <Spinner size="sm" /> : 'Confirm'}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setConfirming(false)} disabled={stopping}>
              ✕
            </Button>
          </div>
        ) : (
          <Button size="sm" variant="secondary" icon={<IconPlayerStop size={13} />} onClick={() => setConfirming(true)}>
            Stop
          </Button>
        )}
      </div>
    </Card>
  );
}

export function OverviewTab() {
  const { app, isLoading } = useAppDetail();
  const metrics = useAppMetrics(app?.slug ?? '');
  const cpuUrl = useMetricUrl(app?.slug ?? '', 'cpu');
  const ramUrl = useMetricUrl(app?.slug ?? '', 'ram');
  const { data: runtimeStatus } = useAppStatus(app?.id);
  const { data: scale } = useAppScaleState(app?.id);
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

      {/* ArgoCD env cards + stop/resume control */}
      {!app?.id || (runtimeStatus?.argocd_error && !runtimeStatus.argocd_prod && !runtimeStatus.argocd_dev) ? (
        <Card>
          <p className="text-xs text-muted-foreground flex items-center gap-1.5">
            <IconAlertTriangle size={12} className="shrink-0" />
            {runtimeStatus?.argocd_error ? `ArgoCD unavailable — ${runtimeStatus.argocd_error}` : 'Unavailable'}
          </p>
        </Card>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          <EnvCard title="Production environment" envKey="prod" appId={app.id} argo={runtimeStatus?.argocd_prod} scaleState={scale?.prod} />
          <EnvCard title="Dev environment" envKey="dev" appId={app.id} argo={runtimeStatus?.argocd_dev} scaleState={scale?.dev} />
        </div>
      )}

      {/* Cloud target */}
      {cluster && (
        <Card>
          <h2 className="text-sm font-medium text-foreground mb-3">Cloud target</h2>
          <div className="flex items-center gap-2">
            {isPrivateCluster(cluster) ? (
              <IconServer size={14} className="text-purple-400 shrink-0" />
            ) : (
              <IconCloud size={14} className="text-blue-400 shrink-0" />
            )}
            <span className={cn(
              'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium',
              isPrivateCluster(cluster) ? 'bg-purple-500/10 text-purple-400' : 'bg-blue-500/10 text-blue-400'
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
        <div className="flex flex-col gap-2">
          {app?.expose && app?.slug ? (
            <>
              <a
                href={appUrl(app.slug, 'prod')}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 text-sm text-[#007BA7] hover:underline"
              >
                <IconExternalLink size={15} />
                <span className="font-mono">{appUrl(app.slug, 'prod')}</span>
                <Badge variant="primary">prod</Badge>
              </a>
              <a
                href={appUrl(app.slug, 'dev')}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 text-sm text-[#007BA7] hover:underline"
              >
                <IconExternalLink size={15} />
                <span className="font-mono">{appUrl(app.slug, 'dev')}</span>
                <Badge variant="muted">dev</Badge>
              </a>
            </>
          ) : (
            <div>
              <p className="text-xs text-muted-foreground mb-1.5 flex items-center gap-1">
                <IconTerminal2 size={13} />
                Local access via port-forward:
              </p>
              <code className="text-xs font-mono bg-background-subtle border border-border px-2.5 py-1.5 rounded block text-foreground select-all">
                kubectl port-forward svc/{app?.slug ?? '<slug>'} 8080:80
              </code>
            </div>
          )}
          {(app?.repo_url ?? app?.source_url) ? (
            <a
              href={(app!.repo_url ?? app!.source_url)!}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground mt-1"
            >
              <IconBrandGitlab size={14} />
              GitLab repository
            </a>
          ) : (
            <span className="flex items-center gap-2 text-xs text-muted-foreground mt-1">
              <IconBrandGitlab size={14} />
              GitLab not configured
            </span>
          )}
        </div>
      </Card>
    </div>
  );
}
