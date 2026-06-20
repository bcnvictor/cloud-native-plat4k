import { useQuery } from '@tanstack/react-query';
import { IconCpu, IconDatabase, IconServer, IconClock, IconCircleCheck } from '@tabler/icons-react';
import { useAppDetail } from '@/layouts/AppDetailLayout';
import { appsApi } from '@/api/apps';
import { monitoringApi } from '@/api/monitoring';
import { MetricCard } from '@/components/MetricCard';
import { Card } from '@/components/ui/Card';
import { AppStatusBadge } from '@/components/AppStatusBadge';
import { Spinner } from '@/components/ui/Spinner';
import { timeAgo } from '@/utils/timeAgo';

const SPARK_CPU = [8,12,10,14,18,16,20,24,22,26,28,25,22,19,23,26,24,22,25,23].map((v,t) => ({ t, v }));
const SPARK_RAM = [32,34,36,38,37,41,43,45,44,47,50,52,50,48,51,53,55,53,52,55].map((v,t) => ({ t, v }));

export function OverviewTab() {
  const { app, isLoading } = useAppDetail();

  const { data: deployments = [] } = useQuery({
    queryKey: ['deployments', app?.id],
    queryFn: () => appsApi.listDeployments(app!.id),
    enabled: !!app,
  });

  const { data: metrics } = useQuery({
    queryKey: ['monitoring-metrics'],
    queryFn: monitoringApi.getMetrics,
    staleTime: 60_000,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Spinner size="lg" />
      </div>
    );
  }

  const appMetric = metrics?.apps?.find((m) => m.app_name === app?.name);
  const currentDeploy = deployments.find((d) => d.status === 'succeeded');

  return (
    <div className="flex flex-col gap-5">
      {/* Metrics */}
      <div className="grid grid-cols-4 gap-4">
        <MetricCard
          label="CPU"
          value={appMetric?.cpu_percent?.toFixed(1) ?? '—'}
          unit="%"
          icon={<IconCpu size={14} />}
          sparkline={SPARK_CPU}
        />
        <MetricCard
          label="RAM"
          value={appMetric ? (appMetric.ram_mb / 1024).toFixed(1) : '—'}
          unit="Gi"
          icon={<IconDatabase size={14} />}
          sparkline={SPARK_RAM}
        />
        <MetricCard
          label="Replicas"
          value="1/1"
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
    </div>
  );
}
