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
  IconUserMinus,
  IconUsers,
  IconWifiOff,
  IconWifi,
  IconHeartbeat,
  IconPencil,
  IconTrash,
  IconHistory,
} from '@tabler/icons-react';
import { Button } from '@/components/ui/Button';
import { useCurrentGroup } from '@/hooks/useCurrentGroup';
import { useGroupApps } from '@/hooks/useGroupApps';
import { useGroupMetrics } from '@/hooks/useAppMetrics';
import { useScopeStore } from '@/store/scope';
import { groupsApi } from '@/api/groups';
import { eventsApi } from '@/api/events';
import { getAppHealth } from '@/utils/appHealth';
import { MetricCard } from '@/components/MetricCard';
import { Card } from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/skeleton';
import { Avatar } from '@/components/Avatar';
import { timeAgo } from '@/utils/timeAgo';
import type { NotificationEvent } from '@/types';

const EVENT_ICON: Record<string, React.ReactNode> = {
  'app.created':          <IconBox size={14} className="text-info-text" />,
  'app.updated':          <IconPencil size={14} className="text-muted-foreground" />,
  'app.deleted':          <IconTrash size={14} className="text-warning-text" />,
  'app.deployed':         <IconRocket size={14} className="text-success-text" />,
  'app.rollback':         <IconHistory size={14} className="text-warning-text" />,
  'app.health.degraded':  <IconAlertTriangle size={14} className="text-danger-text" />,
  'app.health.recovered': <IconHeartbeat size={14} className="text-success-text" />,
  'app.expose.changed':   <IconActivity size={14} className="text-muted-foreground" />,
  'cluster.offline':      <IconWifiOff size={14} className="text-danger-text" />,
  'cluster.online':       <IconWifi size={14} className="text-success-text" />,
  'group.renamed':        <IconPencil size={14} className="text-muted-foreground" />,
  'group.member.added':   <IconUserPlus size={14} className="text-muted-foreground" />,
  'group.member.removed': <IconUserMinus size={14} className="text-muted-foreground" />,
};

function eventLabel(ev: NotificationEvent): string {
  const p = ev.payload ?? {};
  const name = (p.name as string) ?? '';
  switch (ev.type) {
    case 'app.created':          return `${name} was created`;
    case 'app.updated':          return `${name} was updated`;
    case 'app.deleted':          return `${name} was deleted`;
    case 'app.deployed':         return `${name} — deployment successful`;
    case 'app.rollback':         return `${name} — rollback${p.env ? ` (${p.env})` : ''}`;
    case 'app.health.degraded':  return `${name} is degraded`;
    case 'app.health.recovered': return `${name} recovered`;
    case 'app.expose.changed':   return `${name} exposure changed`;
    case 'cluster.offline':      return `Cluster ${p.cluster_name ?? ''} went offline`;
    case 'cluster.online':       return `Cluster ${p.cluster_name ?? ''} is back online`;
    case 'group.renamed':        return `Group renamed to ${p.new_name ?? ''}`;
    case 'group.member.added':   return 'New member joined the group';
    case 'group.member.removed': return 'Member left the group';
    default: return ev.type;
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

  const groupMetrics = useGroupMetrics(apps.map((a) => a.slug));

  const { data: activity = [], isLoading: activityLoading } = useQuery({
    queryKey: ['group-activity', group?.gitlab_group_id],
    queryFn: () => eventsApi.groupActivity(group!.gitlab_group_id, 10),
    enabled: !!group?.gitlab_group_id,
    staleTime: 60_000,
    refetchInterval: 30_000,
  });

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
    <div className="max-w-[1440px] mx-auto px-8 pt-4 pb-6">
      <div className="text-center pt-3 pb-6">
        <p className="text-xs font-semibold uppercase tracking-widest text-zinc-400 mb-2">Overview</p>
        <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-[#007BA7] via-[#4CA5C8] to-[#007BA7] bg-clip-text text-transparent animate-gradient-shift">
          {group?.name ?? '…'}
        </h1>
        <p className="text-xs text-zinc-400 mt-2">
          {apps.length} app{apps.length !== 1 ? 's' : ''} · {members.length} members
        </p>
      </div>

      {/* Metrics row */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <MetricCard
          label="Average CPU"
          value={groupMetrics.available ? groupMetrics.cpu.current.toFixed(1) : '—'}
          unit={groupMetrics.available ? 'm' : undefined}
          icon={<IconCpu size={14} />}
          sublabel={!groupMetrics.available ? (
            <span className="flex items-center gap-1 text-muted-foreground">
              <IconWifiOff size={11} /> Prometheus unavailable
            </span>
          ) : undefined}
        />
        <MetricCard
          label="Total RAM"
          value={groupMetrics.available ? groupMetrics.ram.current.toFixed(0) : '—'}
          unit={groupMetrics.available ? 'MB' : undefined}
          icon={<IconDatabase size={14} />}
        />
        <MetricCard
          label="Apps by status"
          value={statusBadges}
          icon={<IconApps size={14} />}
        />
        <MetricCard
          label="Deployments 7d"
          value={deployments7d}
          sublabel={<span className="text-success-text">+2 vs last week</span>}
          icon={<IconActivity size={14} />}
        />
      </div>

      {/* 2-col grid */}
      <div className="grid grid-cols-2 gap-4">
        {/* Activity */}
        <Card padding="none">
          <div className="px-4 py-3 border-b border-border">
            <h2 className="text-sm font-medium text-foreground">Recent activity</h2>
          </div>
          {activityLoading ? (
            <ul className="divide-y divide-border">
              {Array.from({ length: 5 }).map((_, i) => (
                <li key={i} className="flex items-center gap-3 px-4 py-2.5">
                  <Skeleton className="h-3.5 w-3.5 rounded shrink-0" />
                  <Skeleton className="h-3 flex-1 rounded" />
                  <Skeleton className="h-3 w-12 rounded shrink-0" />
                </li>
              ))}
            </ul>
          ) : activity.length === 0 ? (
            <p className="px-4 py-8 text-sm text-center text-muted-foreground">
              No recent activity
            </p>
          ) : (
            <ul className="divide-y divide-border">
              {activity.map((ev) => (
                <li key={ev.id} className="flex items-center gap-3 px-4 py-2.5">
                  <span className="shrink-0">
                    {EVENT_ICON[ev.type] ?? <IconActivity size={14} className="text-muted-foreground" />}
                  </span>
                  <span className="flex-1 text-xs text-foreground truncate">{eventLabel(ev)}</span>
                  <span className="text-xs text-zinc-400 shrink-0 ml-2">
                    {timeAgo(ev.created_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* Members */}
        <Card padding="none">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border">
            <h2 className="text-sm font-medium text-foreground">Members</h2>
            <button
              onClick={() => navigate(`/groups/${slug}/settings`)}
              className="text-xs font-medium text-primary bg-background/60 border border-primary/20 hover:bg-primary/10 backdrop-blur-sm px-2.5 py-1 rounded-md transition-colors"
            >
              Manage
            </button>
          </div>
          <ul className="divide-y divide-border">
            {members.length === 0 ? (
              <li className="flex flex-col items-center justify-center gap-3 px-4 py-8">
                <IconUsers size={24} className="text-zinc-300" />
                <span className="text-sm text-zinc-400">No members yet</span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => navigate(`/groups/${slug}/settings`)}
                >
                  Invite member
                </Button>
              </li>
            ) : (
              members.map((m, i) => (
                <li key={i} className="flex items-center gap-3 px-4 py-2.5">
                  <Avatar name={m.display_name ?? '?'} size="sm" />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-foreground truncate">
                      {m.display_name ?? <span className="italic text-muted-foreground">Waiting for sync</span>}
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
