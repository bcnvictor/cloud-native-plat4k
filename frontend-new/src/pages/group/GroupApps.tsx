import { useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { IconPlus, IconFilter } from '@tabler/icons-react';
import { useCurrentGroup } from '@/hooks/useCurrentGroup';
import { useGroupApps } from '@/hooks/useGroupApps';
import { useScopeStore } from '@/store/scope';
import { getAppHealth } from '@/utils/appHealth';
import { AppRow } from '@/components/AppRow';
import { Breadcrumb } from '@/components/Breadcrumb';
import { EmptyState } from '@/components/EmptyState';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Spinner } from '@/components/ui/Spinner';
import { computeSlug } from '@/utils/slugify';

export function GroupApps() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const group = useCurrentGroup();
  const { setScope } = useScopeStore();

  useEffect(() => {
    if (slug) setScope('group', slug);
  }, [slug, setScope]);

  const { data: apps = [], isLoading } = useGroupApps(group?.gitlab_group_id);

  return (
    <div className="py-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <Breadcrumb items={[{ label: group?.name ?? '…', to: `/groups/${slug}` }, { label: 'Apps' }]} />
          <h1 className="text-xl font-semibold text-foreground">Apps</h1>
          <p className="text-sm text-muted-foreground">
            {apps.length} application{apps.length !== 1 ? 's' : ''} dans {group?.name ?? '…'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            icon={<IconFilter size={14} />}
          >
            Filtrer
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
        <div className="flex items-center justify-center py-16">
          <Spinner size="lg" />
        </div>
      ) : apps.length === 0 ? (
        <EmptyState
          title="Aucune application"
          description="Créez votre première application pour commencer."
          action={{
            label: 'New app',
            onClick: () => navigate(`/groups/${slug}/apps/new`),
          }}
        />
      ) : (
        <Card padding="none">
          {apps.map((app) => {
            const appSlug = computeSlug(app.name);
            return (
              <AppRow
                key={app.id}
                app={app}
                healthStatus={getAppHealth(app)}
                onClick={() => navigate(`/groups/${slug}/apps/${appSlug}`)}
              />
            );
          })}
        </Card>
      )}
    </div>
  );
}
