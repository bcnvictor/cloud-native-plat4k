import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { IconFilter } from '@tabler/icons-react';
import { useScopeStore } from '@/store/scope';
import { Breadcrumb } from '@/components/Breadcrumb';
import { appsApi } from '@/api/apps';
import { groupsApi } from '@/api/groups';
import { AppStatusBadge } from '@/components/AppStatusBadge';
import { Button } from '@/components/ui/Button';
import { Skeleton } from '@/components/ui/skeleton';
import { getAppHealth } from '@/utils/appHealth';

export function AdminApps() {
  const { setScope } = useScopeStore();
  useEffect(() => { setScope('admin'); }, [setScope]);

  const { data: apps = [], isLoading } = useQuery({
    queryKey: ['apps'],
    queryFn: appsApi.list,
  });

  const { data: groups = [] } = useQuery({
    queryKey: ['my-groups'],
    queryFn: groupsApi.getMyGroups,
    staleTime: 5 * 60 * 1000,
  });

  function groupName(groupId: number | null | undefined): string {
    if (!groupId) return '—';
    const g = groups.find((g) => g.gitlab_group_id === groupId);
    return g?.name ?? `group-${groupId}`;
  }

  return (
    <div className="max-w-[1440px] mx-auto px-8 py-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <Breadcrumb items={[{ label: 'Plateforme', to: '/admin/clusters' }, { label: 'Apps' }]} />
          <h1 className="text-xl font-semibold text-foreground">Apps</h1>
          <p className="text-sm text-muted-foreground">
            {apps.length} application{apps.length !== 1 ? 's' : ''} · toutes équipes
          </p>
        </div>
        <Button variant="secondary" size="sm" icon={<IconFilter size={13} />}>
          Filtrer
        </Button>
      </div>

      <div className="bg-card border border-border rounded-md overflow-hidden">
        {/* Header */}
        <div className="grid grid-cols-[2fr_1fr_1fr_1fr] gap-4 px-4 py-2 border-b border-border bg-background-subtle">
          {['Nom', 'Groupe', 'Cluster', 'Origine'].map((h) => (
            <p key={h} className="text-xs font-medium text-muted-foreground">{h}</p>
          ))}
        </div>

        {isLoading ? (
          Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="px-4 py-3 border-b border-border last:border-0">
              <Skeleton className="h-6 w-full rounded" />
            </div>
          ))
        ) : (
          <>
            {apps.map((app) => {
              const health = getAppHealth(app);
              return (
                <div
                  key={app.id}
                  className="grid grid-cols-[2fr_1fr_1fr_1fr] gap-4 px-4 py-2.5 border-b border-border last:border-0 items-center hover:bg-accent transition-colors"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <AppStatusBadge status={health} showDot size="sm" />
                    <p className="text-sm font-medium text-foreground truncate">{app.name}</p>
                  </div>
                  <p className="text-sm text-muted-foreground truncate">
                    {groupName(app.owning_gitlab_group_id)}
                  </p>
                  <p className="text-xs font-mono text-muted-foreground">—</p>
                  <p className="text-xs text-muted-foreground">{app.origin ?? 'scaffold'}</p>
                </div>
              );
            })}
            {apps.length === 0 && (
              <p className="px-4 py-8 text-sm text-muted-foreground text-center">
                Aucune application.
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
