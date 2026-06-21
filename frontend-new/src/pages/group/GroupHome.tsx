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
  IconUsers,
  IconWifiOff,
} from '@tabler/icons-react';
import { Button } from '@/components/ui/Button';
import { useCurrentGroup } from '@/hooks/useCurrentGroup';
import { useGroupApps } from '@/hooks/useGroupApps';
import { useGroupMetrics } from '@/hooks/useAppMetrics';
import { useScopeStore } from '@/store/scope';
import { groupsApi } from '@/api/groups';
import { getAppHealth } from '@/utils/appHealth';
import { MetricCard } from '@/components/MetricCard';
import { Card } from '@/components/ui/Card';
import { Avatar } from '@/components/Avatar';
import { timeAgo } from '@/utils/timeAgo';
import { ActivityEvent } from '@/types';


// MOCK: pas d'endpoint activity feed — décommissionner quand GET /groups/:id/activity existe
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


export function GroupHome() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const group = useCurrentGroup();
  const { setScope } = useScopeStore();

  useEffect(() => {
    if (slug) setScope('group', slug);
  }, [slug, setScope]);

  const { data: apps = [] } = useGroupApps(group?.gitlab_group_id);

  const { data: members = [] } = useQuery({
    queryKey: ['group-members', group?.gitlab_group_id],
    queryFn: () => groupsApi.getMembers(group!.gitlab_group_id),
    enabled: !!group?.gitlab_group_id,
  });

  const groupMetrics = useGroupMetrics(apps.map((a) => a.name));

  const statusCounts = apps.reduce<Record<string, number>>((acc, a) => {
    const s = getAppHealth(a);
    acc[s] = (acc[s] ?? 0) + 1;
    return acc;
  }, {});

  const STATUS_COLORS: Record<string, { dot: string; label: string }> = {
    healthy:      { dot: 'bg-success',  label: 'text-success-text' },
    deploying:    { dot: 'bg-warning',  label: 'text-warning-text' },
    updating:     { dot: 'bg-warning',  label: 'text-warning-text' },
    unhealthy:    { dot: 'bg-danger',   label: 'text-danger-text' },
    stopped:      { dot: 'bg-zinc-400', label: 'text-zinc-500' },
    provisioning: { dot: 'bg-info',     label: 'text-info-text' },
  };

  const statusBadges = (
    <div className="flex flex-col gap-1">
      {Object.entries(statusCounts).map(([status, count]) => {
        const c = STATUS_COLORS[status] ?? { dot: 'bg-zinc-400', label: 'text-zinc-500' };
        return (
          <span key={status} className="inline-flex items-center gap-1">
            <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${c.dot}`} />
            <span className={`text-xs font-normal ${c.label}`}>{count} {status}</span>
          </span>
        );
      })}
      {apps.length === 0 && (
        <span className="text-xs text-muted-foreground">—</span>
      )}
    </div>
  );

  // MOCK: hardcodé — décommissionner en calculant depuis GET /deployments/?group_id=...&since=7d
  const deployments7d = 12;

  return (
    <div className="max-w-[1440px] mx-auto px-8 pt-8 pb-6">
      <div className="text-center pt-8 pb-6">
        <p className="text-xs font-semibold uppercase tracking-widest text-zinc-400 mb-2">Overview</p>
        <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-[#0C1236] via-[#007BA7] to-[#4CA5C8] bg-clip-text text-transparent">
          {group?.name ?? '…'}
        </h1>
        <p className="text-xs text-zinc-400 mt-2">
          {apps.length} app{apps.length !== 1 ? 's' : ''} · {members.length} membres
        </p>
      </div>

      {/* Metrics row */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <MetricCard
          label="CPU moyen"
          value={groupMetrics.available ? groupMetrics.cpu.current.toFixed(1) : '—'}
          unit={groupMetrics.available ? '%' : undefined}
          icon={<IconCpu size={14} />}
          sublabel={!groupMetrics.available ? (
            <span className="flex items-center gap-1 text-muted-foreground">
              <IconWifiOff size={11} /> Prometheus indisponible
            </span>
          ) : undefined}
        />
        <MetricCard
          label="RAM totale"
          value={groupMetrics.available ? groupMetrics.ram.current.toFixed(0) : '—'}
          unit={groupMetrics.available ? 'MB' : undefined}
          icon={<IconDatabase size={14} />}
        />
        <MetricCard
          label="Apps par statut"
          value={statusBadges}
          icon={<IconApps size={14} />}
        />
        <MetricCard
          label="Deployments 7j"
          value={deployments7d}
          sublabel={<span className="text-success-text">+2 vs semaine dernière</span>}
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
          <ul className="divide-y divide-zinc-100">
            {MOCK_ACTIVITY.map((ev) => (
              <li key={ev.id} className="flex items-center gap-3 px-4 py-2.5">
                <span className="shrink-0">{ACTIVITY_ICON[ev.type]}</span>
                <span className="flex-1 text-xs text-foreground">{activityLabel(ev)}</span>
                <span className="text-xs text-zinc-400 shrink-0">
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
          <ul className="divide-y divide-zinc-100">
            {members.length === 0 ? (
              <li className="flex flex-col items-center justify-center gap-3 px-4 py-8">
                <IconUsers size={24} className="text-zinc-300" />
                <span className="text-sm text-zinc-400">Aucun membre pour l'instant</span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => navigate(`/groups/${slug}/settings`)}
                >
                  Inviter un membre
                </Button>
              </li>
            ) : (
              members.map((m, i) => (
                <li key={i} className="flex items-center gap-3 px-4 py-2.5">
                  <Avatar name={m.display_name ?? '?'} size="sm" />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-foreground truncate">
                      {m.display_name ?? <span className="italic text-muted-foreground">sync en attente</span>}
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
