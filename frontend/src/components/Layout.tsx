import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '@/store/auth';
import { authApi } from '@/api/auth';
import { membersApi } from '@/api/members';

function initials(email: string): string {
  const name = email.split('@')[0];
  const parts = name.split(/[._-]/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

export const Layout = () => {
  const { user, clearAuth, activeGroupId, setActiveGroup } = useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();

  const { data: myGroups = [] } = useQuery({
    queryKey: ['my-groups'],
    queryFn: () => membersApi.getMyGroups(),
    staleTime: 5 * 60 * 1000,
  });

  const syncMutation = useMutation({
    mutationFn: () => membersApi.syncTeams(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['apps'] }),
  });

  const handleLogout = async () => {
    try { await authApi.logout(); } finally {
      clearAuth();
      navigate('/login');
    }
  };

  const matchesPath = (prefixes: string[]) =>
    prefixes.some(p => location.pathname === p || location.pathname.startsWith(p + '/'));

  const navItem = (
    path: string,
    icon: string,
    label: string,
    matchPrefixes?: string[]
  ) => {
    const active = matchesPath(matchPrefixes ?? [path]);
    return (
      <button
        key={path}
        className={`sb-item${active ? ' active' : ''}`}
        onClick={() => navigate(path)}
      >
        <i className={`ti ${icon}`} aria-hidden="true" />
        {label}
      </button>
    );
  };

  return (
    <div className="cnp-layout">
      <aside className="cnp-sidebar">
        <div className="sb-logo">
          <div className="sb-logo-mark">
            <img src="/logo.png" alt="Plat4k" className="sb-logo-icon" width="30" height="30" />
            <div>
              <div className="sb-logo-name">CNP</div>
              <div className="sb-logo-sub">Cloud Native Plat4k</div>
            </div>
          </div>
        </div>

        {myGroups.length > 0 && (
          <div className="sb-team-switcher">
            <div className="sb-team-label">
              <i className="ti ti-users-group" aria-hidden="true" />
              Équipe
            </div>
            <select
              className="sb-team-select"
              value={activeGroupId ?? ''}
              onChange={e => setActiveGroup(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">Toutes les équipes</option>
              {myGroups.map(g => (
                <option key={g.gitlab_group_id} value={g.gitlab_group_id}>
                  {g.name}
                </option>
              ))}
            </select>
          </div>
        )}

        <nav className="sb-nav">
          {navItem('/resources', 'ti-layout-grid', 'Applications', ['/resources', '/'])}
          {navItem('/dashboard', 'ti-activity', 'Monitoring', ['/dashboard'])}
          {navItem('/projects', 'ti-git-branch', 'Mes projets')}
          {user?.role === 'admin' && (
            <>
              <div className="sb-sep" />
              {navItem('/admin/users', 'ti-users', 'Utilisateurs')}
              {navItem('/admin/audit', 'ti-shield-check', 'Audit')}
            </>
          )}
          <div className="sb-sep" />
          {navItem('/docs', 'ti-book', 'Documentation')}
          {navItem('/credentials', 'ti-settings', 'Paramètres', ['/credentials', '/apikeys'])}
        </nav>

        <div className="sb-user">
          <div className="sb-avatar">{initials(user?.email ?? 'U')}</div>
          <div
            style={{ minWidth: 0, flex: 1, cursor: 'pointer' }}
            onClick={() => navigate('/profile')}
            title="Mon profil"
          >
            <div className="sb-user-email">{user?.email}</div>
            <div className="sb-user-role">{user?.role}</div>
          </div>
          <button
            className="sb-logout"
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending}
            title="Synchroniser mes équipes GitLab"
            style={{ marginRight: 4 }}
          >
            <i className={`ti ${syncMutation.isPending ? 'ti-loader-2' : 'ti-refresh'}`} aria-hidden="true"
              style={syncMutation.isPending ? { animation: 'spin 1s linear infinite' } : undefined}
            />
          </button>
          <button className="sb-logout" onClick={handleLogout} title="Déconnexion">
            <i className="ti ti-logout" aria-hidden="true" />
          </button>
        </div>
      </aside>

      <div className="cnp-main">
        <Outlet />
      </div>
    </div>
  );
};
