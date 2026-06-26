import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { IconFilter, IconPlus, IconRocket, IconSearch } from '@tabler/icons-react';
import { useCurrentGroup } from '@/hooks/useCurrentGroup';
import { useGroupApps } from '@/hooks/useGroupApps';
import { useScopeStore } from '@/store/scope';
import { getAppHealth } from '@/utils/appHealth';
import { AppRow } from '@/components/AppRow';
import { useBreadcrumb } from '@/components/nav/BreadcrumbContext';
import { Button } from '@/components/ui/Button';
import { Skeleton } from '@/components/ui/skeleton';

export function GroupApps() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const group = useCurrentGroup();
  const { setScope } = useScopeStore();
  const { setBreadcrumb } = useBreadcrumb();
  const [search, setSearch] = useState('');

  useEffect(() => {
    if (slug) setScope('group', slug);
  }, [slug, setScope]);

  useEffect(() => {
    setBreadcrumb([
      { label: group?.name ?? '…', to: `/groups/${slug}` },
      { label: 'Apps' },
    ]);
    return () => setBreadcrumb([]);
  }, [group?.name, slug, setBreadcrumb]);

  const { data: apps = [], isLoading } = useGroupApps(group?.gitlab_group_id);
  const filteredApps = apps.filter((a) =>
    a.name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="max-w-[1440px] mx-auto px-8 py-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Apps</h1>
          <p className="text-sm text-muted-foreground">
            {apps.length} application{apps.length !== 1 ? 's' : ''} in {group?.name ?? '…'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 px-3 h-8 bg-background border border-border rounded-lg">
            <IconSearch size={14} className="text-muted-foreground shrink-0" />
            <input
              placeholder="Search…"
              className="border-none outline-none text-sm bg-transparent text-foreground placeholder:text-muted-foreground w-40"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <Button
            variant="ghost"
            size="sm"
            icon={<IconFilter size={14} />}
          >
            Filter
          </Button>
          <Button
            variant="primary"
            size="sm"
            icon={<IconPlus size={14} />}
            onClick={() => navigate(`/groups/${slug}/apps/new`)}
          >
            New app
          </Button>
        </div>
      </div>

      {/* List */}
      {isLoading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-[60px] w-full rounded-lg" />
          ))}
        </div>
      ) : filteredApps.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 gap-4">
          <IconRocket size={40} className="text-zinc-300" />
          <div className="flex flex-col items-center gap-1">
            <p className="text-sm font-medium text-zinc-500">No applications</p>
            <p className="text-xs text-zinc-400">Create your first app to get started</p>
          </div>
          <Button
            variant="primary"
            size="sm"
            icon={<IconPlus size={14} />}
            onClick={() => navigate(`/groups/${slug}/apps/new`)}
          >
            New app
          </Button>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {filteredApps.map((app) => {
            return (
              <AppRow
                key={app.id}
                app={app}
                healthStatus={getAppHealth(app)}
                onClick={() => navigate(`/groups/${slug}/apps/${app.slug}`)}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
