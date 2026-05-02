import { Outlet, Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '@/store/auth';
import { authApi } from '@/api/auth';
import {
  LayoutDashboard,
  Server,
  Key,
  ShieldAlert,
  Users,
  LogOut,
  Database
} from 'lucide-react';
import { clsx } from 'clsx';

export const Layout = () => {
  const { user, clearAuth } = useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = async () => {
    try {
      await authApi.logout();
    } finally {
      clearAuth();
      navigate('/login');
    }
  };

  const navItems = [
    { name: 'Dashboard', path: '/dashboard', icon: LayoutDashboard },
    { name: 'Resources', path: '/resources', icon: Server },
    { name: 'Credentials', path: '/credentials', icon: Key },
    { name: 'API Keys', path: '/apikeys', icon: Database },
  ];

  const adminItems = [
    { name: 'Users', path: '/admin/users', icon: Users },
    { name: 'Audit Logs', path: '/admin/audit', icon: ShieldAlert },
  ];

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <div className="w-64 bg-white border-r border-gray-200 flex flex-col">
        <div className="p-6 border-b border-gray-200">
          <h1 className="text-xl font-bold text-gray-900">Cloud Platform</h1>
        </div>

        <nav className="flex-1 overflow-y-auto p-4 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname.startsWith(item.path);
            return (
              <Link
                key={item.path}
                to={item.path}
                className={clsx(
                  'flex items-center px-4 py-2 text-sm font-medium rounded-md',
                  isActive
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-gray-700 hover:bg-gray-50'
                )}
              >
                <Icon className={clsx('mr-3 h-5 w-5', isActive ? 'text-blue-700' : 'text-gray-400')} />
                {item.name}
              </Link>
            );
          })}

          {user?.role === 'admin' && (
            <>
              <div className="mt-8 mb-2 px-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Admin
              </div>
              {adminItems.map((item) => {
                const Icon = item.icon;
                const isActive = location.pathname.startsWith(item.path);
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    className={clsx(
                      'flex items-center px-4 py-2 text-sm font-medium rounded-md',
                      isActive
                        ? 'bg-blue-50 text-blue-700'
                        : 'text-gray-700 hover:bg-gray-50'
                    )}
                  >
                    <Icon className={clsx('mr-3 h-5 w-5', isActive ? 'text-blue-700' : 'text-gray-400')} />
                    {item.name}
                  </Link>
                );
              })}
            </>
          )}
        </nav>

        <div className="p-4 border-t border-gray-200">
          <div className="flex items-center justify-between">
            <div className="text-sm">
              <p className="font-medium text-gray-900 truncate w-32">{user?.email}</p>
              <p className="text-gray-500 capitalize">{user?.role}</p>
            </div>
            <button
              onClick={handleLogout}
              className="p-2 text-gray-400 hover:text-gray-500 rounded-md hover:bg-gray-100"
              title="Logout"
            >
              <LogOut className="h-5 w-5" />
            </button>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 overflow-auto">
        <main className="p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
