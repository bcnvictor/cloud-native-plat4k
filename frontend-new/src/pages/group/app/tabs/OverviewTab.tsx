import { useQuery } from '@tanstack/react-query';
import { IconAlertTriangle, IconBrandGitlab, IconCircleCheck, IconClock, IconCpu, IconDatabase, IconServer } from '@tabler/icons-react';
import { useAppDetail } from '@/layouts/AppDetailLayout';
import { appsApi } from '@/api/apps';
import { MetricCard } from '@/components/MetricCard';
import { Card } from '@/components/ui/Card';
import { AppStatusBadge } from '@/components/AppStatusBadge';
import { Spinner } from '@/components/ui/Spinner';
import { timeAgo } from '@/utils/timeAgo';
import { useAppMetrics } from '@/hooks/useAppMetrics';
import { useMonitoringConfig, useGrafanaMetricUrl } from '@/hooks/useMonitoringConfig';

export function OverviewTab() {
  const { app, isLoading } = useAppDetail();
  const metrics = useAppMetrics(app?.name ?? '');
  const grafanaUrl = useMonitoringConfig();
  const cpuGrafanaUrl = useGrafanaMetricUrl(grafanaUrl, app?.name ?? '', 'cpu');
  const ramGrafanaUrl = useGrafanaMetricUrl(grafanaUrl, app?.name ?? '', 'ram');

  const { data: deployments = [] } = useQuery({
    queryKey: ['deployments', app?.id],
    queryFn: () => appsApi.listDeployments(app!.id),
    enabled: !!app,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Spinner size="lg" />
      </div>
    );
  }

  const currentDeploy = deployments.find((d) => d.status === 'succeeded');

  return (
    <div className="flex flex-col gap-5">
      {/* Metrics */}
      <div className="grid grid-cols-4 gap-4">
        {!metrics.available && (
          <div className="col-span-4 flex items-center gap-2 px-3 py-2 rounded-md bg-muted/40 border border-border text-xs text-muted-foreground">
            <IconAlertTriangle size={13} className="shrink-0" />
            Métriques indisponibles — vérifier la connexion Prometheus
          </div>
        )}
        <MetricCard
          label="CPU"
          value={metrics.available ? metrics.cpu.current.toFixed(1) : '—'}
          unit={metrics.available ? '%' : undefined}
          icon={<IconCpu size={14} />}
          sparkline={metrics.cpu.series}
          externalUrl={cpuGrafanaUrl ?? undefined}
        />
        <MetricCard
          label="RAM"
          value={metrics.available ? metrics.ram.current.toFixed(0) : '—'}
          unit={metrics.available ? metrics.ramUnit : undefined}
          icon={<IconDatabase size={14} />}
          sparkline={metrics.ram.series}
          externalUrl={ramGrafanaUrl ?? undefined}
        />
        <MetricCard
          label="Replicas"
          value={metrics.replicas.current}
          icon={<IconServer size={14} />}
        />
        <MetricCard
          label="Uptime"
          value={currentDeploy ? timeAgo(currentDeploy.deployed_at) : '—'}
          icon={<IconClock size={14} />}
        />
      </div>

      {/* 2-col */}
      <div className="grid grid-cols-2 gap-4">
        {/* Current deployment */}
        <Card>
          <h2 className="text-sm font-medium text-foreground mb-3">Déploiement courant</h2>
          {currentDeploy ? (
            <dl className="flex flex-col gap-2">
              {[
                { label: 'Commit', value: currentDeploy.version, mono: true },
                // MOCK: branch et trigger hardcodés — décommissionner quand stockés en DB
                { label: 'Branche', value: 'main', mono: true },
                { label: 'Déployé', value: timeAgo(currentDeploy.deployed_at) },
                { label: 'Cluster', value: `cluster-${currentDeploy.cluster_id}`, mono: true },
                { label: 'Trigger', value: 'commit' },
              ].map(({ label, value, mono }) => (
                <div key={label} className="flex items-baseline gap-2">
                  <dt className="text-xs text-muted-foreground w-20 shrink-0">{label}</dt>
                  <dd className={`text-xs text-foreground ${mono ? 'font-mono' : ''}`}>
                    {value}
                  </dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-xs text-muted-foreground">Aucun déploiement réussi.</p>
          )}
        </Card>

        {/* Injected services */}
        {/* MOCK: liste hardcodée PostgreSQL+Redis toujours "healthy" — décommissionner quand GET /apps/:id/services existe */}
        <Card>
          <h2 className="text-sm font-medium text-foreground mb-3">Services injectés</h2>
          <ul className="flex flex-col gap-2">
            {[
              { name: 'PostgreSQL', id: 'postgres', status: 'healthy' as const },
              { name: 'Redis', id: 'redis', status: 'healthy' as const },
            ].map((svc) => (
              <li key={svc.id} className="flex items-center gap-2">
                <IconCircleCheck size={14} className="text-success-text shrink-0" />
                <span className="text-xs font-mono text-foreground flex-1">{svc.id}</span>
                <span className="text-xs text-foreground">{svc.name}</span>
                <AppStatusBadge status={svc.status} size="sm" />
              </li>
            ))}
            <li className="pt-2 mt-1 border-t border-border">
              <span className="text-xs text-muted-foreground">
                Port exposé : <span className="font-mono">8080</span>
              </span>
            </li>
          </ul>
        </Card>
      </div>

      {/* Quick access */}
      <Card>
        <h2 className="text-sm font-medium text-foreground mb-3">Accès rapide</h2>
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
            GitLab non configuré
          </span>
        )}
      </Card>
    </div>
  );
}
