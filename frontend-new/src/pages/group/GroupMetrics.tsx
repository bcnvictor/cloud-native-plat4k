import { useQuery } from '@tanstack/react-query';
import { IconChartBar, IconExternalLink } from '@tabler/icons-react';
import { useCurrentGroup } from '@/hooks/useCurrentGroup';
import { groupsApi } from '@/api/groups';

export function GroupMetrics() {
  const group = useCurrentGroup();

  const { data, isLoading } = useQuery({
    queryKey: ['group-grafana-url', group?.gitlab_group_id],
    queryFn: () => groupsApi.getGrafanaUrl(group!.gitlab_group_id),
    enabled: !!group?.gitlab_group_id,
  });

  if (isLoading || !group) {
    return (
      <div className="flex items-center justify-center h-64 text-muted-foreground text-sm">
        Loading…
      </div>
    );
  }

  if (!data?.url) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 h-64 text-center px-8">
        <IconChartBar size={32} className="text-zinc-300" />
        <p className="text-sm font-medium text-foreground">No dashboard yet</p>
        <p className="text-xs text-muted-foreground max-w-sm">
          {group.name} has no apps yet, or Grafana is not configured.
          Scaffold an app first — its metrics will appear here automatically.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-56px)]">
      <div className="flex items-center justify-between px-6 py-2 border-b border-border shrink-0">
        <span className="text-xs text-muted-foreground">
          {group.name} — metrics dashboard
        </span>
        <a
          href={data.url.replace('&kiosk', '')}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1 text-xs text-primary hover:underline"
        >
          <IconExternalLink size={12} />
          Open in Grafana
        </a>
      </div>
      <iframe
        src={data.url}
        className="flex-1 w-full border-0"
        title={`${group.name} metrics`}
      />
    </div>
  );
}
