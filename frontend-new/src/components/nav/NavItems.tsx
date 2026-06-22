import { NavLink } from 'react-router-dom';
import {
  IconHome,
  IconApps,
  IconChartBar,
  IconSettings,
  IconServer,
  IconCoin,
  IconUsers,
  IconShield,
} from '@tabler/icons-react';
import { useScopeStore } from '@/store/scope';
import { cn } from '@/utils/cn';

interface NavItemDef {
  label: string;
  icon: React.ElementType;
  path: (slug: string) => string;
}

const GROUP_NAV: NavItemDef[] = [
  { label: 'Home',     icon: IconHome,     path: (slug) => `/groups/${slug}` },
  { label: 'Apps',     icon: IconApps,     path: (slug) => `/groups/${slug}/apps` },
  { label: 'Metrics',  icon: IconChartBar, path: (slug) => `/groups/${slug}/metrics` },
  { label: 'Settings', icon: IconSettings, path: (slug) => `/groups/${slug}/settings` },
];

const ADMIN_NAV: NavItemDef[] = [
  { label: 'Clusters',     icon: IconServer,   path: () => '/admin/clusters' },
  { label: 'Apps',         icon: IconApps,     path: () => '/admin/apps' },
  { label: 'FinOps',       icon: IconCoin,     path: () => '/admin/finops' },
  { label: 'Users',        icon: IconUsers,    path: () => '/admin/users' },
  { label: 'Audit',        icon: IconShield,   path: () => '/admin/audit' },
  { label: 'Settings',     icon: IconSettings, path: () => '/admin/settings' },
];

interface NavItemsProps {
  collapsed?: boolean;
}

export function NavItems({ collapsed = false }: NavItemsProps) {
  const { activeScope, activeGroupSlug } = useScopeStore();
  const items = activeScope === 'admin' ? ADMIN_NAV : GROUP_NAV;
  const slug = activeGroupSlug ?? '';

  return (
    <nav className="flex flex-col gap-0.5 px-2">
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <NavLink
            key={item.label}
            to={item.path(slug)}
            end={item.label === 'Home'}
            title={collapsed ? item.label : undefined}
            className={({ isActive }) =>
              cn(
                'flex items-center rounded-md text-sm transition-colors',
                collapsed ? 'justify-center px-0 py-2' : 'gap-2.5 px-3 py-2',
                isActive
                  ? 'bg-[#007BA7]/9 text-[#007BA7] font-medium'
                  : 'text-muted-foreground hover:bg-muted hover:text-foreground'
              )
            }
          >
            <Icon size={16} className="shrink-0" />
            {!collapsed && <span>{item.label}</span>}
          </NavLink>
        );
      })}
    </nav>
  );
}
