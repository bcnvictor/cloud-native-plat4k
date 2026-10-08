import { useEffect } from 'react';
import { Navigate, NavLink, useParams } from 'react-router-dom';
import { IconBrandGitlab, IconLayoutDashboard, IconRobot, IconServer2 } from '@tabler/icons-react';
import { useScopeStore } from '@/store/scope';
import { useBreadcrumb } from '@/components/nav/BreadcrumbContext';
import { cn } from '@/utils/cn';
import { OverviewPanel } from './settings/OverviewPanel';
import { ClusterConnectionsPanel } from './settings/ClusterConnectionsPanel';
import { GitLabGroupsPanel } from './settings/GitLabGroupsPanel';
import { AIAssistantPanel } from './settings/AIAssistantPanel';

// Control center : config globale plateforme. Un panneau n'est ajouté ici
// que lorsque sa feature backend existe (cf. 4K-85).
const PANELS = [
  { key: 'overview', label: 'Overview', icon: IconLayoutDashboard, group: null, element: <OverviewPanel /> },
  { key: 'clusters', label: 'Clusters', icon: IconServer2, group: 'Connections', element: <ClusterConnectionsPanel /> },
  { key: 'gitlab', label: 'GitLab groups', icon: IconBrandGitlab, group: 'Connections', element: <GitLabGroupsPanel /> },
  { key: 'ai', label: 'AI assistant', icon: IconRobot, group: 'Services', element: <AIAssistantPanel /> },
] as const;

const UPCOMING = [
  { label: 'Scale-to-zero', ticket: '4K-82' },
  { label: 'GitLab polling', ticket: '4K-66' },
  { label: 'Vault', ticket: '4K-60' },
  { label: 'Alerting', ticket: '4K-72' },
];

export function AdminSettings() {
  const params = useParams<{ panel?: string }>();
  const panel = params.panel ?? 'overview';
  const { setScope } = useScopeStore();
  const { setBreadcrumb } = useBreadcrumb();
  const active = PANELS.find((p) => p.key === panel);

  useEffect(() => { setScope('admin'); }, [setScope]);

  useEffect(() => {
    setBreadcrumb([
      { label: 'Platform', to: '/admin/clusters' },
      { label: 'Settings', to: '/admin/settings' },
      { label: active?.label ?? '' },
    ]);
    return () => setBreadcrumb([]);
  }, [setBreadcrumb, active]);

  // /admin/settings/overview → URL canonique, pour que le lien Overview soit actif.
  if (!active || params.panel === 'overview') return <Navigate to="/admin/settings" replace />;

  let lastGroup: string | null = null;

  return (
    <div className="max-w-[1440px] mx-auto px-8 py-6">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-foreground">Control center</h1>
        <p className="text-sm text-muted-foreground">
          Global platform configuration. Every change is recorded in the audit log.
        </p>
      </div>

      <div className="grid gap-8 lg:grid-cols-[200px_minmax(0,1fr)] items-start">
        <nav aria-label="Control center panels" className="flex flex-wrap lg:flex-col gap-0.5 lg:sticky lg:top-4">
          {PANELS.map((p) => {
            const showGroup = p.group !== null && p.group !== lastGroup;
            lastGroup = p.group;
            const Icon = p.icon;
            return (
              <div key={p.key} className="contents">
                {showGroup && (
                  <p className="hidden lg:block text-[11px] uppercase tracking-wide text-muted-foreground px-2.5 pt-3 pb-1">
                    {p.group}
                  </p>
                )}
                <NavLink
                  to={p.key === 'overview' ? '/admin/settings' : `/admin/settings/${p.key}`}
                  end
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-2 px-2.5 py-1.5 rounded-md text-sm transition-colors',
                      isActive
                        ? 'bg-[#007BA7]/9 text-[#007BA7] font-medium'
                        : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                    )
                  }
                >
                  <Icon size={14} className="shrink-0" />
                  {p.label}
                </NavLink>
              </div>
            );
          })}
          <p className="hidden lg:block text-[11px] uppercase tracking-wide text-muted-foreground px-2.5 pt-3 pb-1">
            Coming soon
          </p>
          {UPCOMING.map((u) => (
            <span
              key={u.ticket}
              className="hidden lg:flex items-center gap-2 px-2.5 py-1.5 text-sm text-muted-foreground opacity-60"
            >
              {u.label}
              <span className="ml-auto font-mono text-[10px] px-1.5 rounded bg-muted">{u.ticket}</span>
            </span>
          ))}
        </nav>

        <div className="min-w-0">{active.element}</div>
      </div>
    </div>
  );
}
