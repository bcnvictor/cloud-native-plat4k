import { IconSearch, IconBell } from '@tabler/icons-react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/store/auth';
import { authApi } from '@/api/auth';
import { ScopeSwitcher } from './ScopeSwitcher';
import { NavItems } from './NavItems';
import { Avatar } from '@/components/Avatar';
import { Dropdown } from '@/components/ui/Dropdown';

export function TopNav() {
  const { user, clearAuth } = useAuthStore();
  const navigate = useNavigate();

  async function handleLogout() {
    await authApi.logout().catch(() => null);
    clearAuth();
    navigate('/login');
  }

  return (
    <header
      className="fixed top-0 left-0 right-0 z-40 flex items-center h-12 px-4 border-b border-zinc-200 bg-white shadow-[0_1px_3px_rgba(0,0,0,0.06)]"
    >
      {/* Logo */}
      <Link to="/" className="shrink-0">
        <div className="w-6 h-6 rounded-md bg-[#0C1236] flex items-center justify-center overflow-hidden">
          <img src="/favicon.svg" className="w-4 h-4 object-contain" alt="CNP" />
        </div>
      </Link>

      {/* Divider */}
      <div className="w-px h-4 bg-border mx-2 shrink-0" />

      {/* Left: scope switcher */}
      <div className="flex items-center shrink-0 mr-4">
        <ScopeSwitcher />
      </div>

      {/* Center: primary nav */}
      <div className="flex-1 flex justify-center">
        <NavItems />
      </div>

      {/* Right: search + bell + avatar */}
      <div className="flex items-center gap-1 ml-4">
        <button
          className="h-7 w-7 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
          aria-label="Rechercher"
        >
          <IconSearch size={16} />
        </button>
        <button
          className="h-7 w-7 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
          aria-label="Notifications"
        >
          <IconBell size={16} />
        </button>

        {user && (
          <Dropdown
            trigger={
              <button className="ml-1">
                <Avatar name={user.email} size="md" className="bg-primary text-primary-foreground" />
              </button>
            }
            items={[
              {
                key: 'email',
                label: user.email,
                disabled: true,
              },
              {
                key: 'logout',
                label: 'Se déconnecter',
                divider: true,
                onClick: handleLogout,
              },
            ]}
            align="right"
            width={200}
          />
        )}
      </div>
    </header>
  );
}
