import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { IconBrandGitlab, IconMoon } from '@tabler/icons-react';
import { adminApi } from '@/api/admin';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { Spinner } from '@/components/ui/Spinner';
import { timeAgo } from '@/utils/timeAgo';

const hour = (h: number) => `${String(h).padStart(2, '0')}:00`;

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2 border-b border-border last:border-0 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-foreground text-right tabular-nums">{children}</span>
    </div>
  );
}

function ScheduleCard({ icon, title, enabled, offLabel, children, footer }: {
  icon: ReactNode;
  title: string;
  enabled: boolean;
  offLabel: string;
  children: ReactNode;
  footer: ReactNode;
}) {
  return (
    <Card>
      <div className="flex items-center justify-between gap-3 mb-2">
        <h2 className="flex items-center gap-2 text-sm font-medium text-foreground">{icon}{title}</h2>
        <Badge variant={enabled ? 'success' : 'muted'}>{enabled ? 'Enabled' : offLabel}</Badge>
      </div>
      <div className="flex flex-col">{children}</div>
      <p className="mt-3 text-xs text-muted-foreground">{footer}</p>
    </Card>
  );
}

export function SchedulesPanel() {
  const { data, isLoading } = useQuery({ queryKey: ['platform-schedules'], queryFn: adminApi.getPlatformSchedules });
  const { data: groups = [] } = useQuery({ queryKey: ['admin-gitlab-groups'], queryFn: adminApi.listGitlabGroups });

  if (isLoading || !data) {
    return <div className="flex justify-center py-16"><Spinner size="lg" /></div>;
  }

  const s2z = data.scale_to_zero;
  const lastSync = groups.map((g) => g.synced_at).filter((d): d is string => Boolean(d)).sort().pop();

  return (
    <div className="grid gap-4 lg:grid-cols-2 items-start">
      <ScheduleCard
        icon={<IconMoon size={15} className="text-muted-foreground" />}
        title="Dev scale-to-zero"
        enabled={s2z.enabled}
        offLabel="Disabled"
        footer={<>Set by the backend variables <span className="font-mono">SCALE_SCHEDULE_ENABLED</span> and <span className="font-mono">DEV_SCALE_*</span>, applied at restart.</>}
      >
        <Row label="Dev environments stop">{hour(s2z.scale_down_hour)}</Row>
        <Row label="Dev environments restart">{hour(s2z.scale_up_hour)}{s2z.weekdays_only ? ', weekdays only' : ', every day'}</Row>
        <Row label="Timezone">{s2z.timezone}</Row>
        <Row label="Reconciliation">every {s2z.interval_minutes} min</Row>
        {!s2z.enabled && (
          <p className="pt-2 text-xs text-muted-foreground">
            Off: dev environments keep running at night. Each app can still be stopped by hand from its Overview.
          </p>
        )}
      </ScheduleCard>

      <ScheduleCard
        icon={<IconBrandGitlab size={15} className="text-muted-foreground" />}
        title="GitLab membership sync"
        enabled={data.gitlab_sync.enabled}
        offLabel="No GitLab token"
        footer={<>Interval set by <span className="font-mono">GITLAB_SYNC_INTERVAL_MINUTES</span>, applied at restart.</>}
      >
        <Row label="Mirrors members of">
          <Link to="/admin/users/gitlab-groups" className="text-primary hover:underline">
            {groups.length} GitLab group{groups.length !== 1 ? 's' : ''}
          </Link>
        </Row>
        <Row label="Runs">every {data.gitlab_sync.interval_minutes} min</Row>
        <Row label="Last sync">{lastSync ? timeAgo(lastSync) : 'never'}</Row>
      </ScheduleCard>
    </div>
  );
}
