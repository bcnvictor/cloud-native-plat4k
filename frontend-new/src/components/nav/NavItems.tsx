import { NavLink, useLocation } from 'react-router-dom';
import {
  IconHome,
  IconApps,
  IconChartBar,
  IconSettings,
  IconServer,
  IconCoin,
  IconUsers,
  IconShield,
  IconPackage,
} from '@tabler/icons-react';
import { useScopeStore } from '@/store/scope';
import { cn } from '@/utils/cn';

interface NavChildDef {
  label: string;
  path: string;
}

interface NavItemDef {
  label: string;
  icon: React.ElementType;
  path: (slug: string) => string;
  // Sous-pages révélées sous l'entrée quand elle est active. Le lien parent mène à la première.
  children?: NavChildDef[];
}

const GROUP_NAV: NavItemDef[] = [
  { label: 'Home',     icon: IconHome,     path: (slug) => `/groups/${slug}` },
  { label: 'Apps',     icon: IconApps,     path: (slug) => `/groups/${slug}/apps` },
  { label: 'Metrics',  icon: IconChartBar, path: (slug) => `/groups/${slug}/metrics` },
  { label: 'Settings', icon: IconSettings, path: (slug) => `/groups/${slug}/settings` },
];

const ADMIN_NAV: NavItemDef[] = [
  {
    label: 'Clusters', icon: IconServer, path: () => '/admin/clusters',
    children: [
      { label: 'Status', path: '/admin/clusters' },
      { label: 'Connections', path: '/admin/clusters/connections' },
    ],
  },
  { label: 'Apps',         icon: IconApps,    path: () => '/admin/apps' },
  { label: 'FinOps',       icon: IconCoin,    path: () => '/admin/finops' },
  {
    label: 'Users', icon: IconUsers, path: () => '/admin/users',
    children: [
      { label: 'Users', path: '/admin/users' },
      { label: 'GitLab groups', path: '/admin/users/gitlab-groups' },
    ],
  },
  { label: 'Dependencies', icon: IconPackage, path: () => '/admin/dependencies' },
  { label: 'Audit',        icon: IconShield,  path: () => '/admin/audit' },
  {
    label: 'Settings', icon: IconSettings, path: () => '/admin/settings',
    children: [
      { label: 'Overview', path: '/admin/settings' },
      { label: 'AI assistant', path: '/admin/settings/ai' },
      { label: 'Schedules', path: '/admin/settings/schedules' },
    ],
  },
];

interface NavItemsProps {
  collapsed?: boolean;
}

const itemClass = (active: boolean) =>
  active
    ? 'bg-[#007BA7]/9 text-[#007BA7] font-medium'
    : 'text-muted-foreground hover:bg-muted hover:text-foreground';

export function NavItems({ collapsed = false }: NavItemsProps) {
  const { activeScope, activeGroupSlug } = useScopeStore();
  const { pathname } = useLocation();
  const items = activeScope === 'admin' ? ADMIN_NAV : GROUP_NAV;
  const slug = activeGroupSlug ?? '';

  return (
    <nav className="flex flex-col gap-0.5 px-2">
      {items.map((item) => {
        const Icon = item.icon;
        const base = item.path(slug);
        const open = !!item.children && (pathname === base || pathname.startsWith(`${base}/`));
        return (
          <div key={item.label} className="flex flex-col gap-0.5">
            <NavLink
              to={base}
              end={item.label === 'Home'}
              title={collapsed ? item.label : undefined}
              aria-expanded={item.children ? open : undefined}
              className={({ isActive }) =>
                cn(
                  'flex items-center rounded-md text-sm transition-colors',
                  collapsed ? 'justify-center px-0 py-2' : 'gap-2.5 px-3 py-2',
                  open
                    ? 'text-[#007BA7] font-medium hover:bg-muted'
                    : itemClass(isActive)
                )
              }
            >
              <Icon size={16} className="shrink-0" />
              {!collapsed && <span>{item.label}</span>}
            </NavLink>
            {open && !collapsed && (
              <div className="ml-[19px] flex flex-col gap-0.5 border-l border-border pl-2 py-0.5">
                {item.children!.map((child) => (
                  <NavLink
                    key={child.path}
                    to={child.path}
                    end
                    className={({ isActive }) =>
                      cn(
                        'rounded-md px-2.5 py-1.5 text-[13px] transition-colors',
                        isActive
                          ? 'text-[#007BA7] font-medium bg-[#007BA7]/9'
                          : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                      )
                    }
                  >
                    {child.label}
                  </NavLink>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </nav>
  );
}
