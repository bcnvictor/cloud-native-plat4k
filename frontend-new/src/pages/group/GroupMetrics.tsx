import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  IconLayoutDashboard,
  IconCoin,
  IconCpu,
  IconActivity,
  IconTerminal2,
  IconExternalLink,
} from '@tabler/icons-react';
import { useCurrentGroup } from '@/hooks/useCurrentGroup';
import { useTheme } from '@/contexts/ThemeContext';
import { groupsApi } from '@/api/groups';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs } from '@/components/ui/Tabs';
import { cn } from '@/utils/cn';

const VIEW_TABS = [
  { key: 'overview', label: 'Overview' },
  { key: 'deep-dive', label: 'Deep Dive' },
];

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
  const src = `${baseUrl}&panelId=${panelId}&theme=${theme}&refresh=30s&hideLogo=true`;

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
      {/* Blocks panel header hover zone (title + Explore/Edit menu) */}
      <div className="absolute top-0 left-0 right-0 h-11 z-10 cursor-default" />
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

interface TabContentProps {
  baseUrl: string;
  theme: string;
  dashboardUrl: string | null;
}

function OverviewContent({ baseUrl, theme }: TabContentProps) {
  return (
    <>
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
    </>
  );
}

function DeepDiveContent({ baseUrl, theme, dashboardUrl }: TabContentProps) {
  return (
    <>
      <SectionHeader icon={IconCpu} label="Compute" />
      <div className="grid grid-cols-2 gap-3 mb-6">
        <GrafanaPanel panelId={21} title="CPU par app" baseUrl={baseUrl} theme={theme} height={260} />
        <GrafanaPanel panelId={22} title="RAM par app" baseUrl={baseUrl} theme={theme} height={260} />
      </div>

      <SectionHeader icon={IconActivity} label="Santé" />
      <div className="grid grid-cols-2 gap-3 mb-6">
        <GrafanaPanel panelId={31} title="Restarts par pod" baseUrl={baseUrl} theme={theme} height={220} />
        <GrafanaPanel panelId={32} title="Pod readiness"    baseUrl={baseUrl} theme={theme} height={220} />
      </div>

      <SectionHeader icon={IconTerminal2} label="Logs" />
      <GrafanaPanel panelId={41} title="Logs" baseUrl={baseUrl} theme={theme} height={320} />

      {dashboardUrl && (
        <div className="mt-4 flex justify-end">
          <a
            href={dashboardUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <IconExternalLink size={13} />
            Ouvrir dans Grafana
          </a>
        </div>
      )}
    </>
  );
}

export function GroupMetrics() {
  const group = useCurrentGroup();
  const { theme } = useTheme();
  const [activeTab, setActiveTab] = useState('overview');

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
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold">{group.name} — métriques</h2>
        {dashboardUrl && activeTab === 'overview' && (
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

      <Tabs tabs={VIEW_TABS} active={activeTab} onChange={setActiveTab} className="mb-6" />

      {activeTab === 'overview' ? (
        <OverviewContent baseUrl={baseUrl} theme={theme} dashboardUrl={dashboardUrl} />
      ) : (
        <DeepDiveContent baseUrl={baseUrl} theme={theme} dashboardUrl={dashboardUrl} />
      )}

      <div className="h-6" />
    </div>
  );
}
