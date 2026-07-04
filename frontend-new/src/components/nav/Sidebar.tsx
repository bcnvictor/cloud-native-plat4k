import { IconChevronLeft, IconChevronRight, IconRobot } from '@tabler/icons-react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '@/store/auth';
import { authApi } from '@/api/auth';
import { Avatar } from '@/components/Avatar';
import { Dropdown } from '@/components/ui/Dropdown';
import { NavItems } from './NavItems';
import { ScopeSwitcher } from './ScopeSwitcher';
import { NotificationBell } from './NotificationBell';
import { cn } from '@/utils/cn';

interface SidebarProps {
  expanded: boolean;
  onToggle: () => void;
  assistantOpen?: boolean;
  onAssistantToggle?: () => void;
}

export function Sidebar({ expanded, onToggle, assistantOpen, onAssistantToggle }: SidebarProps) {
  const { user, clearAuth } = useAuthStore();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  async function handleLogout() {
    await authApi.logout().catch(() => null);
    clearAuth();
    queryClient.clear();
    navigate('/login');
  }

  const profileDropdown = user ? (
    <Dropdown
      trigger={
        <button title={user.email}>
          <Avatar name={user.email} size="md" className="bg-primary text-primary-foreground" />
        </button>
      }
      items={[
        { key: 'email', label: user.email, disabled: true },
        { key: 'profile', label: 'My profile', onClick: () => navigate('/profile') },
        { key: 'logout', label: 'Sign out', divider: true, onClick: handleLogout },
      ]}
      side="top"
      align="left"
      width={200}
    />
  ) : (
    <div className="h-8 w-8" />
  );

  return (
    <aside
      className="flex flex-col bg-sidebar border-r border-sidebar-border shrink-0 transition-[width] duration-200 ease-in-out"
      style={{ width: expanded ? '216px' : '52px', height: '100%' }}
    >
      {/* Zone logo + collapse toggle */}
      <div className="flex items-center h-12 px-3 border-b border-border shrink-0 overflow-hidden">
        <div className="w-7 h-7 rounded-md bg-[#0C1236] flex items-center justify-center shrink-0">
          <img src="/favicon.svg" className="w-4 h-4 object-contain" alt="CNP" />
        </div>
        {expanded && (
          <>
            <span className="ml-2.5 text-sm font-semibold text-primary whitespace-nowrap">
              Plat4k
            </span>
            <button
              onClick={onToggle}
              className="ml-auto h-6 w-6 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
              aria-label="Collapse sidebar"
            >
              <IconChevronLeft size={14} />
            </button>
          </>
        )}
      </div>

      {/* Zone context switcher / expand toggle */}
      <div className={`shrink-0 px-1 pt-2 ${!expanded ? 'flex justify-center' : ''}`}>
        {expanded ? (
          <ScopeSwitcher collapsed={false} />
        ) : (
          <button
            onClick={onToggle}
            className="h-7 w-7 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
            aria-label="Expand sidebar"
          >
            <IconChevronRight size={14} />
          </button>
        )}
      </div>

      {/* Zone nav */}
      <div className="flex-1 overflow-y-auto py-2 min-h-0">
        <NavItems collapsed={!expanded} />
      </div>

      {/* Zone footer — bell + AI button au-dessus du profil en collapsed */}
      <div className={`shrink-0 border-t border-border p-3 ${expanded ? 'flex items-center justify-between' : 'flex flex-col items-center gap-3'}`}>
        {expanded ? (
          <>
            {profileDropdown}
            <div className="flex items-center gap-1">
              <button
                onClick={onAssistantToggle}
                title="AI Assistant"
                className={cn(
                  'h-7 w-7 flex items-center justify-center rounded-md transition-colors',
                  assistantOpen
                    ? 'bg-primary/10 text-primary'
                    : 'text-muted-foreground hover:text-foreground hover:bg-accent'
                )}
              >
                <IconRobot size={15} />
              </button>
              <NotificationBell />
            </div>
          </>
        ) : (
          <>
            <button
              onClick={onAssistantToggle}
              title="AI Assistant"
              className={cn(
                'h-7 w-7 flex items-center justify-center rounded-md transition-colors',
                assistantOpen
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground hover:text-foreground hover:bg-accent'
              )}
            >
              <IconRobot size={15} />
            </button>
            <NotificationBell />
            {profileDropdown}
          </>
        )}
      </div>
    </aside>
  );
}
