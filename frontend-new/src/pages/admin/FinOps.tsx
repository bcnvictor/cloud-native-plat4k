import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { IconAlertTriangle, IconExternalLink } from '@tabler/icons-react';
import { useScopeStore } from '@/store/scope';
import { useBreadcrumb } from '@/components/nav/BreadcrumbContext';
import { useTheme } from '@/contexts/ThemeContext';
import { finopsApi } from '@/api/finops';
import { Card } from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/skeleton';
import { FinopsCostByTeamChart } from '@/components/FinopsCostByTeamChart';
import { cn } from '@/utils/cn';

interface GrafanaPanelProps {
  src: string | null;
  title: string;
  theme: string;
  height: number;
  className?: string;
}

function GrafanaPanel({ src, title, theme, height, className }: GrafanaPanelProps) {
  const [loaded, setLoaded] = useState(false);

  if (!src) {
    return (
      <div
        className={cn('flex items-center justify-center rounded-lg border border-border bg-background text-center px-4', className)}
        style={{ height }}
      >
        <p className="text-xs text-muted-foreground">Grafana not configured</p>
      </div>
    );
  }

  const fullSrc = `${src}&theme=${theme}&refresh=30s&hideLogo=true`;

  return (
    <div
      className={cn('relative rounded-lg overflow-hidden bg-background', className)}
      style={{ height }}
    >
      {!loaded && (
        <Skeleton className="absolute inset-0 h-full rounded-lg" />
      )}
      <iframe
        src={fullSrc}
        title={title}
        allow="fullscreen"
        className="w-full h-full border-0"
        onLoad={() => setLoaded(true)}
      />
      {/* Blocks panel header hover zone (title + Explore/Edit menu) */}
      <div className="absolute top-0 left-0 right-0 h-11 z-10 cursor-default" />
    </div>
  );
}

export function FinOps() {
  const { setScope } = useScopeStore();
  const { setBreadcrumb } = useBreadcrumb();
  const { theme } = useTheme();
  useEffect(() => { setScope('admin'); }, [setScope]);

  useEffect(() => {
    setBreadcrumb([{ label: 'Platform', to: '/admin/clusters' }, { label: 'FinOps' }]);
    return () => setBreadcrumb([]);
  }, [setBreadcrumb]);

  const { data: urls, isLoading } = useQuery({
    queryKey: ['finops-grafana-urls'],
    queryFn: () => finopsApi.getGrafanaUrls(),
    staleTime: 60_000,
  });

  return (
    <div className="max-w-[1440px] mx-auto px-8 py-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-foreground">FinOps</h1>
        {urls?.dashboard_url && (
          <a
            href={urls.dashboard_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <IconExternalLink size={13} />
            Open in Grafana
          </a>
        )}
      </div>

      <div className="flex items-start gap-2 rounded-lg border border-warning-border bg-warning-subtle px-4 py-3 mb-6 text-sm text-warning-text">
        <IconAlertTriangle size={16} className="shrink-0 mt-0.5" />
        <p>
          <span className="font-medium">Oracle (k3s) temporarily unmonitored</span> — costs shown are AKS only.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-4">
        {isLoading ? (
          <>
            <Skeleton className="h-[140px] rounded-lg" />
            <Skeleton className="h-[140px] rounded-lg col-span-2" />
          </>
        ) : (
          <>
            <GrafanaPanel src={urls?.total_cost_panel_url ?? null} title="Total AKS cost (30d)" theme={theme} height={140} />
            <GrafanaPanel src={urls?.trend_panel_url ?? null} title="Recent cost trend (30d)" theme={theme} height={140} className="col-span-2" />
          </>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Card>
          <h2 className="text-sm font-medium text-foreground mb-4">Top 5 most expensive apps</h2>
          {isLoading ? (
            <Skeleton className="h-[280px] rounded-lg" />
          ) : (
            <GrafanaPanel src={urls?.top_apps_panel_url ?? null} title="Top 5 most expensive apps" theme={theme} height={280} />
          )}
        </Card>

        <Card>
          <h2 className="text-sm font-medium text-foreground mb-4">Cost by team</h2>
          <FinopsCostByTeamChart />
        </Card>
      </div>
    </div>
  );
}
