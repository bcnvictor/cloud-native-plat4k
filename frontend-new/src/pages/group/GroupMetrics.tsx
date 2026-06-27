import { useState } from 'react';
import { IconLayoutDashboard, IconCoin, IconExternalLink } from '@tabler/icons-react';
import { useCurrentGroup } from '@/hooks/useCurrentGroup';
import { useTheme } from '@/contexts/ThemeContext';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/utils/cn';

const GRAFANA_HOST = 'https://grafana.cloud-native-plat4k.me';
const DASHBOARD_UID = 'amc2nv';
const DASHBOARD_SLUG = 'cnp-e28094-group-overview';

function buildPanelUrl(panelId: number, groupId: number, theme: string): string {
  const params = new URLSearchParams({
    orgId: '1',
    panelId: String(panelId),
    'var-group_id': String(groupId),
    theme,
    refresh: '30s',
  });
  return `${GRAFANA_HOST}/d-solo/${DASHBOARD_UID}/${DASHBOARD_SLUG}?${params}`;
}

interface PanelProps {
  panelId: number;
  title: string;
  groupId: number;
  theme: string;
  height: number;
  className?: string;
}

function GrafanaPanel({ panelId, title, groupId, theme, height, className }: PanelProps) {
  const [loaded, setLoaded] = useState(false);
  const src = buildPanelUrl(panelId, groupId, theme);

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
      {/* Blocks the panel header hover menu (Explore, Edit…) */}
      <div className="absolute top-0 left-0 right-0 h-8 z-10 cursor-default" />
      {/* Covers the "Powered by Grafana" footer */}
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

  if (!group) {
    return (
      <div className="flex items-center justify-center h-64 text-muted-foreground text-sm">
        Chargement…
      </div>
    );
  }

  const gid = group.gitlab_group_id;
  const grafanaUrl = `${GRAFANA_HOST}/d/${DASHBOARD_UID}/${DASHBOARD_SLUG}?orgId=1&var-group_id=${gid}`;

  return (
    <div className="px-6 py-4">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-sm font-semibold">{group.name} — métriques</h2>
        <a
          href={grafanaUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <IconExternalLink size={13} />
          Voir tout dans Grafana
        </a>
      </div>

      <SectionHeader icon={IconLayoutDashboard} label="Vue d'ensemble" />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <GrafanaPanel panelId={2}  title="Apps actives"    groupId={gid} theme={theme} height={140} />
        <GrafanaPanel panelId={3}  title="Pods Running"    groupId={gid} theme={theme} height={140} />
        <GrafanaPanel panelId={4}  title="Coût estimé 30j" groupId={gid} theme={theme} height={140} />
        <GrafanaPanel panelId={5}  title="Restart count"   groupId={gid} theme={theme} height={140} />
      </div>

      <SectionHeader icon={IconCoin} label="FinOps Showback" />
      <div className="grid grid-cols-3 gap-3">
        <GrafanaPanel panelId={11} title="Coût par app"     groupId={gid} theme={theme} height={280} className="col-span-2" />
        <GrafanaPanel panelId={12} title="Répartition coût" groupId={gid} theme={theme} height={280} />
      </div>

      <div className="h-6" />
    </div>
  );
}
