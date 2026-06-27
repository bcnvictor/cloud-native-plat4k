import { useState } from 'react';
import {
  IconLayoutDashboard,
  IconCoin,
  IconCpu,
  IconActivity,
  IconTerminal2,
} from '@tabler/icons-react';
import { useCurrentGroup } from '@/hooks/useCurrentGroup';
import { useTheme } from '@/contexts/ThemeContext';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs } from '@/components/ui/Tabs';
import { cn } from '@/utils/cn';

const GRAFANA_BASE = 'https://grafana.cloud-native-plat4k.me/d-solo/amc2nv/cnp-e28094-group-overview';

const ENV_TABS = [
  { key: 'all', label: 'All' },
  { key: 'dev', label: 'Dev' },
  { key: 'prod', label: 'Prod' },
];

function buildUrl(panelId: number, groupId: number, env: string, theme: string): string {
  const params = new URLSearchParams({
    orgId: '1',
    panelId: String(panelId),
    'var-group_id': String(groupId),
    theme,
    refresh: '30s',
  });
  if (env !== 'all') params.set('var-env', env);
  return `${GRAFANA_BASE}?${params}`;
}

interface PanelProps {
  panelId: number;
  title: string;
  groupId: number;
  env: string;
  theme: string;
  height: number;
  className?: string;
}

function GrafanaPanel({ panelId, title, groupId, env, theme, height, className }: PanelProps) {
  const [loaded, setLoaded] = useState(false);
  const src = buildUrl(panelId, groupId, env, theme);

  return (
    <div className={cn('relative rounded-lg overflow-hidden', className)} style={{ height }}>
      {!loaded && <Skeleton className="absolute inset-0 h-full rounded-lg dark:bg-zinc-800" />}
      <iframe
        key={src}
        src={src}
        title={title}
        allow="fullscreen"
        className="w-full h-full border-0"
        onLoad={() => setLoaded(true)}
      />
    </div>
  );
}

interface SectionProps {
  icon: React.ElementType;
  label: string;
}

function Section({ icon: Icon, label }: SectionProps) {
  return (
    <div className="flex items-center gap-2 mb-3 mt-6 first:mt-0">
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
  const [env, setEnv] = useState('all');

  if (!group) {
    return (
      <div className="flex items-center justify-center h-64 text-muted-foreground text-sm">
        Chargement…
      </div>
    );
  }

  const gid = group.gitlab_group_id;

  return (
    <div className="px-6 py-4">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-sm font-semibold">{group.name} — métriques</h2>
        <Tabs tabs={ENV_TABS} active={env} onChange={setEnv} />
      </div>

      <Section icon={IconLayoutDashboard} label="Vue d'ensemble" />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <GrafanaPanel panelId={2}  title="Apps actives"     groupId={gid} env={env} theme={theme} height={120} />
        <GrafanaPanel panelId={3}  title="Pods Running"     groupId={gid} env={env} theme={theme} height={120} />
        <GrafanaPanel panelId={4}  title="Coût estimé 30j"  groupId={gid} env={env} theme={theme} height={120} />
        <GrafanaPanel panelId={5}  title="Restart count"    groupId={gid} env={env} theme={theme} height={120} />
      </div>

      <Section icon={IconCoin} label="FinOps Showback" />
      <div className="grid grid-cols-3 gap-3">
        <GrafanaPanel panelId={11} title="Coût par app"       groupId={gid} env={env} theme={theme} height={280} className="col-span-2" />
        <GrafanaPanel panelId={12} title="Répartition coût"   groupId={gid} env={env} theme={theme} height={280} />
      </div>

      <Section icon={IconCpu} label="Compute" />
      <div className="grid grid-cols-2 gap-3">
        <GrafanaPanel panelId={21} title="CPU par app" groupId={gid} env={env} theme={theme} height={260} />
        <GrafanaPanel panelId={22} title="RAM par app" groupId={gid} env={env} theme={theme} height={260} />
      </div>

      <Section icon={IconActivity} label="Santé" />
      <div className="grid grid-cols-2 gap-3">
        <GrafanaPanel panelId={31} title="Restarts par pod"  groupId={gid} env={env} theme={theme} height={220} />
        <GrafanaPanel panelId={32} title="Pod readiness"     groupId={gid} env={env} theme={theme} height={220} />
      </div>

      <Section icon={IconTerminal2} label="Logs" />
      <GrafanaPanel panelId={41} title="Logs" groupId={gid} env={env} theme={theme} height={320} />

      <div className="h-6" />
    </div>
  );
}
