import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '@/store/auth';
import { authApi } from '@/api/auth';
import { HexLogo } from '@/components/HexLogo';

function initials(email: string): string {
  const name = email.split('@')[0];
  const parts = name.split(/[._-]/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

export const Layout = () => {
  const { user, clearAuth } = useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();

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
            <div className="sb-logo-icon"><HexLogo size={16} /></div>
            <div>
              <div className="sb-logo-name">CNP</div>
              <div className="sb-logo-sub">Cloud Native Plat4k</div>
            </div>
          </div>
        </div>

        <nav className="sb-nav">
          {navItem('/resources', 'ti-layout-grid', 'Applications', ['/resources', '/'])}
          {navItem('/dashboard', 'ti-activity', 'Monitoring', ['/dashboard'])}
          {navItem('/projects', 'ti-git-branch', 'Mes projets')}
          <div className="sb-sep" />
          {navItem('/docs', 'ti-book', 'Documentation')}
          <div className="sb-sep" />
          {navItem('/credentials', 'ti-settings', 'Paramètres', ['/credentials', '/apikeys'])}
          {user?.role === 'admin' && (
            <>
              <div className="sb-sep" />
              {navItem('/admin/users', 'ti-users', 'Utilisateurs')}
              {navItem('/admin/audit', 'ti-shield-check', 'Audit')}
            </>
          )}
        </nav>

        <div className="sb-user">
          <div className="sb-avatar">{initials(user?.email ?? 'U')}</div>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div className="sb-user-email">{user?.email}</div>
            <div className="sb-user-role">{user?.role}</div>
          </div>
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
