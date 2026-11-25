import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { clustersApi } from '@/api/clusters';
import { adminApi } from '@/api/admin';
import { assistantApi } from '@/api/assistant';
import { Badge } from '@/components/ui/Badge';
import { timeAgo } from '@/utils/timeAgo';
import { ALL_CONFIG_ACTIONS, ConfigHistory } from './ConfigHistory';

function Tile({ label, badge, value, sub, onClick }: {
  label: string;
  badge?: ReactNode;
  value: ReactNode;
  sub: string;
  onClick?: () => void;
}) {
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag
      onClick={onClick}
      className={
        onClick
          ? 'text-left flex flex-col gap-2 px-4 py-3.5 rounded-lg border border-border bg-background hover:border-primary-border transition-colors'
          : 'text-left flex flex-col gap-2 px-4 py-3.5 rounded-lg border border-dashed border-border'
      }
    >
      <span className="flex items-center justify-between gap-2 text-xs text-muted-foreground">{label}{badge}</span>
      <span className="text-xl font-semibold text-foreground tabular-nums">{value}</span>
      <span className="text-xs text-muted-foreground">{sub}</span>
    </Tag>
  );
}

export function OverviewPanel() {
  const navigate = useNavigate();
  const { data: clusters = [] } = useQuery({ queryKey: ['clusters'], queryFn: clustersApi.list });
  const { data: groups = [] } = useQuery({ queryKey: ['admin-gitlab-groups'], queryFn: adminApi.listGitlabGroups });
  const { data: ai } = useQuery({ queryKey: ['ai-global-settings'], queryFn: assistantApi.getGlobalSettings, retry: false });
  const { data: schedules } = useQuery({ queryKey: ['platform-schedules'], queryFn: adminApi.getPlatformSchedules });
  const s2z = schedules?.scale_to_zero;
  const hh = (h: number) => `${String(h).padStart(2, '0')}:00`;

  const online = clusters.filter((c) => c.status === 'online').length;
  const offline = clusters.filter((c) => c.status === 'offline').length;
  const apps = clusters.reduce((n, c) => n + c.app_count, 0);
  const syncDates = groups
    .map((g) => g.synced_at)
    .filter((d): d is string => Boolean(d))
    .sort();
  const lastSync = syncDates[syncDates.length - 1];

  return (
    <div className="flex flex-col gap-5">
      <div className="grid gap-3 grid-cols-[repeat(auto-fit,minmax(200px,1fr))]">
        <Tile
          label="Clusters"
          badge={offline > 0 ? <Badge variant="danger">{offline} offline</Badge> : undefined}
          value={<>{online}<span className="text-sm font-normal text-muted-foreground"> / {clusters.length} online</span></>}
          sub={`${apps} app${apps !== 1 ? 's' : ''} deployed · Manage connections →`}
          onClick={() => navigate('/admin/clusters/connections')}
        />
        <Tile
          label="GitLab groups"
          value={<>{groups.length}<span className="text-sm font-normal text-muted-foreground"> synchronized</span></>}
          sub={lastSync ? `Last sync ${timeAgo(lastSync)}` : 'Never synchronized'}
          onClick={() => navigate('/admin/users/gitlab-groups')}
        />
        <Tile
          label="AI assistant"
          badge={ai ? <Badge variant="primary">{ai.provider}</Badge> : undefined}
          value={ai ? (ai.assistant_enabled ? 'Enabled' : 'Disabled') : '—'}
          sub={ai?.platform_data_access_enabled ? 'CNP data access on' : 'CNP data access off'}
          onClick={() => navigate('/admin/settings/ai')}
        />
        <Tile
          label="Dev scale-to-zero"
          badge={s2z ? <Badge variant={s2z.enabled ? 'success' : 'muted'}>{s2z.enabled ? 'On' : 'Off'}</Badge> : undefined}
          value={s2z ? `${hh(s2z.scale_down_hour)} → ${hh(s2z.scale_up_hour)}` : '—'}
          sub={schedules ? `GitLab sync every ${schedules.gitlab_sync.interval_minutes} min · Schedules →` : 'Schedules →'}
          onClick={() => navigate('/admin/settings/schedules')}
        />
      </div>
      <ConfigHistory title="Recent configuration changes" actions={ALL_CONFIG_ACTIONS} />
    </div>
  );
}
