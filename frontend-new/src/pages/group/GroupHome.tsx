import React, { useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  IconCpu,
  IconDatabase,
  IconApps,
  IconActivity,
  IconRocket,
  IconAlertTriangle,
  IconBox,
  IconUserPlus,
} from '@tabler/icons-react';
import { useCurrentGroup } from '@/hooks/useCurrentGroup';
import { useGroupApps } from '@/hooks/useGroupApps';
import { useScopeStore } from '@/store/scope';
import { useAuthStore } from '@/store/auth';
import { monitoringApi } from '@/api/monitoring';
import { appsApi } from '@/api/apps';
import { MetricCard } from '@/components/MetricCard';
import { Card } from '@/components/ui/Card';
import { Avatar } from '@/components/Avatar';
import { timeAgo } from '@/utils/timeAgo';
import { ActivityEvent } from '@/types';
import { getAppHealth } from '@/utils/appHealth';

const SPARK_CPU = [22,28,24,31,40,38,45,52,48,55,58,54,60,57,51,47,43,49,53,50].map((v,t) => ({ t, v }));
const SPARK_RAM = [42,44,47,49,48,52,55,57,60,62,64,61,65,68,70,72,69,71,73,74].map((v,t) => ({ t, v }));

const MOCK_ACTIVITY: ActivityEvent[] = [
  { id: '1', type: 'deploy_success', appName: 'auth-service', timestamp: new Date(Date.now() - 1000 * 60 * 12).toISOString() },
  { id: '2', type: 'provisioning', appName: 'api-gateway', timestamp: new Date(Date.now() - 1000 * 60 * 45).toISOString() },
  { id: '3', type: 'deploy_failed', appName: 'worker', timestamp: new Date(Date.now() - 1000 * 60 * 90).toISOString() },
  { id: '4', type: 'member_added', memberName: 'Alice Martin', timestamp: new Date(Date.now() - 1000 * 60 * 180).toISOString() },
  { id: '5', type: 'deploy_success', appName: 'frontend-app', timestamp: new Date(Date.now() - 1000 * 60 * 60 * 5).toISOString() },
];

const ACTIVITY_ICON: Record<ActivityEvent['type'], React.ReactNode> = {
  deploy_success: <IconRocket size={14} className="text-success-text" />,
  deploy_failed: <IconAlertTriangle size={14} className="text-danger-text" />,
  provisioning: <IconBox size={14} className="text-info-text" />,
  replica_error: <IconAlertTriangle size={14} className="text-warning-text" />,
  member_added: <IconUserPlus size={14} className="text-muted-foreground" />,
};

function activityLabel(ev: ActivityEvent): string {
  switch (ev.type) {
    case 'deploy_success': return `${ev.appName} — déploiement réussi`;
    case 'deploy_failed': return `${ev.appName} — déploiement échoué`;
    case 'provisioning': return `${ev.appName} — provisioning en cours`;
    case 'replica_error': return `${ev.appName} — replica en erreur`;
    case 'member_added': return `${ev.memberName} a rejoint le groupe`;
    default: return '';
  }
}

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 18) return 'Good afternoon';
  return 'Good evening';
}

function firstNameFromEmail(email: string): string {
  const local = email.split('@')[0];
  const part = local.split(/[._-]/)[0];
  return part.charAt(0).toUpperCase() + part.slice(1);
}

export function GroupHome() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const group = useCurrentGroup();
  const { setScope } = useScopeStore();
  const { user } = useAuthStore();

  useEffect(() => {
    if (slug) setScope('group', slug);
  }, [slug, setScope]);

  const { data: apps = [] } = useGroupApps(group?.gitlab_group_id);
  const { data: metrics } = useQuery({
    queryKey: ['monitoring-metrics'],
    queryFn: monitoringApi.getMetrics,
    staleTime: 60_000,
  });

  const groupAppIds = apps.map((a) => a.id);
  const { data: members = [] } = useQuery({
    queryKey: ['members', groupAppIds[0]],
    queryFn: () => (groupAppIds[0] ? appsApi.getMembers(groupAppIds[0]) : Promise.resolve([])),
    enabled: groupAppIds.length > 0,
  });

  const healthyCount = apps.filter((a) => getAppHealth(a) === 'healthy').length;
  const deployments7d = 12; // mock

  const groupMetrics = metrics?.apps?.filter((m) =>
    apps.some((a) => a.name === m.app_name)
  );
  const totalCpu = groupMetrics?.reduce((s, m) => s + m.cpu_percent, 0) ?? 0;
  const totalRam = groupMetrics?.reduce((s, m) => s + m.ram_mb, 0) ?? 0;

  return (
    <div className="py-6">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-foreground">{group?.name ?? '…'}</h1>
        <p className="text-sm text-muted-foreground">
          {user ? `${greeting()}, ${firstNameFromEmail(user.email)} · ` : ''}
          {apps.length} app{apps.length !== 1 ? 's' : ''} · {members.length} membres
        </p>
      </div>

      {/* Metrics row */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <MetricCard
          label="CPU agrégé"
          value={totalCpu.toFixed(1)}
          unit="%"
          icon={<IconCpu size={14} />}
          sparkline={SPARK_CPU}
        />
        <MetricCard
          label="RAM agrégée"
          value={(totalRam / 1024).toFixed(1)}
          unit="Gi"
          icon={<IconDatabase size={14} />}
          sparkline={SPARK_RAM}
        />
        <MetricCard
          label="Apps par statut"
          value={`${healthyCount}/${apps.length}`}
          sublabel="healthy"
          icon={<IconApps size={14} />}
        />
        <MetricCard
          label="Deployments 7j"
          value={deployments7d}
          icon={<IconActivity size={14} />}
        />
      </div>

      {/* 2-col grid */}
      <div className="grid grid-cols-2 gap-4">
        {/* Activity */}
        <Card padding="none">
          <div className="px-4 py-3 border-b border-border">
            <h2 className="text-sm font-medium text-foreground">Activité récente</h2>
          </div>
          <ul className="divide-y divide-border">
            {MOCK_ACTIVITY.map((ev) => (
              <li key={ev.id} className="flex items-center gap-3 px-4 py-2.5">
                <span className="shrink-0">{ACTIVITY_ICON[ev.type]}</span>
                <span className="flex-1 text-xs text-foreground">{activityLabel(ev)}</span>
                <span className="text-xs text-muted-foreground shrink-0">
                  {timeAgo(ev.timestamp)}
                </span>
              </li>
            ))}
          </ul>
        </Card>

        {/* Members */}
        <Card padding="none">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border">
            <h2 className="text-sm font-medium text-foreground">Membres</h2>
            <button
              onClick={() => navigate(`/groups/${slug}/settings`)}
              className="text-xs font-medium text-[#007BA7] bg-[#D9F0F7] px-2.5 py-1 rounded-md hover:bg-[#B3DAEB] transition-colors"
            >
              Gérer
            </button>
          </div>
          <ul className="divide-y divide-border">
            {members.length === 0 ? (
              <li className="px-4 py-3 text-xs text-muted-foreground">Aucun membre</li>
            ) : (
              members.map((m, i) => (
                <li key={i} className="flex items-center gap-3 px-4 py-2.5">
                  <Avatar name={m.display_name ?? m.email ?? 'U'} size="sm" />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-foreground truncate">
                      {m.display_name ?? m.email}
                    </p>
                    <p className="text-xs text-muted-foreground">{m.tier_cnp}</p>
                  </div>
                </li>
              ))
            )}
          </ul>
        </Card>
      </div>
    </div>
  );
}
