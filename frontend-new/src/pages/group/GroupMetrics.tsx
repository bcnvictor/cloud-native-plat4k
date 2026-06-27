import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { IconLayoutDashboard, IconCoin, IconExternalLink } from '@tabler/icons-react';
import { useCurrentGroup } from '@/hooks/useCurrentGroup';
import { useTheme } from '@/contexts/ThemeContext';
import { groupsApi } from '@/api/groups';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/utils/cn';

interface PanelProps {
  panelId: number;
  title: string;
  baseUrl: string;
  theme: string;
  height: number;
  className?: string;
}

function GrafanaPanel({ panelId, title, baseUrl, theme, height, className }: PanelProps) {
  const [loaded, setLoaded] = useState(false);
  const src = `${baseUrl}&panelId=${panelId}&theme=${theme}&refresh=30s`;

  return (
    <div
      className={cn('relative rounded-lg overflow-hidden bg-background', className)}
      style={{ height }}
    >
      {!loaded && (
        <Skeleton className="absolute inset-0 h-full rounded-lg dark:bg-zinc-800" />
      )}
      <iframe
        src={src}
        title={title}
        allow="fullscreen"
        className="w-full h-full border-0"
        onLoad={() => setLoaded(true)}
      />
      {/* Intercepts panel header hover menu (Explore, Edit…) */}
      <div className="absolute top-0 left-0 right-0 h-8 z-10 cursor-default" />
      {/* Covers "Powered by Grafana" footer */}
      <div className="absolute bottom-0 left-0 right-0 h-5 z-10 bg-background" />
    </div>
  );
}

function SectionHeader({ icon: Icon, label }: { icon: React.ElementType; label: string }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <Icon size={14} className="text-muted-foreground shrink-0" />
      <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider whitespace-nowrap">
        {label}
      </span>
      <div className="flex-1 h-px bg-border" />
    </div>
  );
}

export function GroupMetrics() {
  const group = useCurrentGroup();
  const { theme } = useTheme();

  const { data, isLoading } = useQuery({
    queryKey: ['group-grafana-url', group?.gitlab_group_id],
    queryFn: () => groupsApi.getGrafanaUrl(group!.gitlab_group_id),
    enabled: !!group?.gitlab_group_id,
  });

  if (!group || isLoading) {
    return (
      <div className="flex items-center justify-center h-64 text-muted-foreground text-sm">
        Chargement…
      </div>
    );
  }

  if (!data?.panel_base_url) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 h-64 text-center px-8">
        <p className="text-sm font-medium">Métriques non disponibles</p>
        <p className="text-xs text-muted-foreground max-w-sm">
          Aucune app déployée pour ce groupe, ou Grafana n'est pas encore configuré.
        </p>
      </div>
    );
  }

  const { panel_base_url: baseUrl, dashboard_url: dashboardUrl } = data;

  return (
    <div className="px-6 py-4">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-sm font-semibold">{group.name} — métriques</h2>
        {dashboardUrl && (
          <a
            href={dashboardUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <IconExternalLink size={13} />
            Voir tout dans Grafana
          </a>
        )}
      </div>

      <SectionHeader icon={IconLayoutDashboard} label="Vue d'ensemble" />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <GrafanaPanel panelId={2}  title="Apps actives"    baseUrl={baseUrl} theme={theme} height={140} />
        <GrafanaPanel panelId={3}  title="Pods Running"    baseUrl={baseUrl} theme={theme} height={140} />
        <GrafanaPanel panelId={4}  title="Coût estimé 30j" baseUrl={baseUrl} theme={theme} height={140} />
        <GrafanaPanel panelId={5}  title="Restart count"   baseUrl={baseUrl} theme={theme} height={140} />
      </div>

      <SectionHeader icon={IconCoin} label="FinOps Showback" />
      <div className="grid grid-cols-3 gap-3">
        <GrafanaPanel panelId={11} title="Coût par app"     baseUrl={baseUrl} theme={theme} height={280} className="col-span-2" />
        <GrafanaPanel panelId={12} title="Répartition coût" baseUrl={baseUrl} theme={theme} height={280} />
      </div>

      <div className="h-6" />
    </div>
  );
}
