import { useEffect, type ReactNode } from 'react';
import { Navigate, useParams } from 'react-router-dom';
import { useScopeStore } from '@/store/scope';
import { useBreadcrumb, type BreadcrumbItem } from '@/components/nav/BreadcrumbContext';
import { OverviewPanel } from './settings/OverviewPanel';
import { ClusterConnectionsPanel } from './settings/ClusterConnectionsPanel';
import { GitLabGroupsPanel } from './settings/GitLabGroupsPanel';
import { AIAssistantPanel } from './settings/AIAssistantPanel';
import { SchedulesPanel } from './settings/SchedulesPanel';

// Pages de configuration plateforme, rangées sous leur section de la sidebar admin
// (Clusters, Users, Settings). Chaque changement est tracé dans l'audit.
function AdminPanelPage({ breadcrumb, title, description, children }: {
  breadcrumb: BreadcrumbItem[];
  title?: string;
  description?: string;
  children: ReactNode;
}) {
  const { setScope } = useScopeStore();
  const { setBreadcrumb } = useBreadcrumb();
  const crumbs = JSON.stringify(breadcrumb);

  useEffect(() => { setScope('admin'); }, [setScope]);
  useEffect(() => {
    setBreadcrumb([{ label: 'Platform', to: '/admin/clusters' }, ...JSON.parse(crumbs)]);
    return () => setBreadcrumb([]);
  }, [setBreadcrumb, crumbs]);

  return (
    <div className="max-w-[1440px] mx-auto px-8 py-6">
      {title && (
        <div className="mb-6">
          <h1 className="text-xl font-semibold text-foreground">{title}</h1>
          {description && <p className="text-sm text-muted-foreground">{description}</p>}
        </div>
      )}
      {children}
    </div>
  );
}

export function AdminClusterConnections() {
  return (
    <AdminPanelPage breadcrumb={[{ label: 'Clusters', to: '/admin/clusters' }, { label: 'Connections' }]}>
      <ClusterConnectionsPanel />
    </AdminPanelPage>
  );
}

export function AdminGitlabGroups() {
  return (
    <AdminPanelPage breadcrumb={[{ label: 'Users', to: '/admin/users' }, { label: 'GitLab groups' }]}>
      <GitLabGroupsPanel />
    </AdminPanelPage>
  );
}

export function AdminSettings() {
  return (
    <AdminPanelPage
      breadcrumb={[{ label: 'Settings' }]}
      title="Settings"
      description="Global platform configuration. Every change is recorded in the audit log."
    >
      <OverviewPanel />
    </AdminPanelPage>
  );
}

export function AdminAISettings() {
  return (
    <AdminPanelPage
      breadcrumb={[{ label: 'Settings', to: '/admin/settings' }, { label: 'AI assistant' }]}
      title="AI assistant"
      description="Provider, platform-wide switches and the apps the assistant may read."
    >
      <AIAssistantPanel />
    </AdminPanelPage>
  );
}

export function AdminSchedules() {
  return (
    <AdminPanelPage
      breadcrumb={[{ label: 'Settings', to: '/admin/settings' }, { label: 'Schedules' }]}
      title="Schedules"
      description="Background jobs run by the platform. Read-only: they are set by backend environment variables."
    >
      <SchedulesPanel />
    </AdminPanelPage>
  );
}

// Anciennes URL du control center (/admin/settings/<panel>) : liens et favoris existants.
const LEGACY_PANELS: Record<string, string> = {
  overview: '/admin/settings',
  clusters: '/admin/clusters/connections',
  gitlab: '/admin/users/gitlab-groups',
};

export function AdminSettingsLegacyRedirect() {
  const { panel = '' } = useParams<{ panel: string }>();
  return <Navigate to={LEGACY_PANELS[panel] ?? '/admin/settings'} replace />;
}
