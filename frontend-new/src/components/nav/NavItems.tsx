import { NavLink } from 'react-router-dom';
import { useScopeStore } from '@/store/scope';
import { cn } from '@/utils/cn';

const GROUP_NAV = [
  { label: 'Home', path: (slug: string) => `/groups/${slug}` },
  { label: 'Apps', path: (slug: string) => `/groups/${slug}/apps` },
  { label: 'Settings', path: (slug: string) => `/groups/${slug}/settings` },
];

const ADMIN_NAV = [
  { label: 'Clusters', path: () => '/admin/clusters' },
  { label: 'FinOps', path: () => '/admin/finops' },
  { label: 'Apps', path: () => '/admin/apps' },
  { label: 'Utilisateurs', path: () => '/admin/users' },
  { label: 'Audit', path: () => '/admin/audit' },
  { label: 'Settings', path: () => '/admin/settings' },
];

export function NavItems() {
  const { activeScope, activeGroupSlug } = useScopeStore();
  const items = activeScope === 'admin' ? ADMIN_NAV : GROUP_NAV;
  const slug = activeGroupSlug ?? '';

  return (
    <nav className="flex items-center gap-1">
      {items.map((item) => (
        <NavLink
          key={item.label}
          to={item.path(slug)}
          end={item.label === 'Home'}
          className={({ isActive }) =>
            cn(
              'px-3 py-1.5 rounded-md text-sm font-medium transition-colors',
              isActive
                ? 'text-[#007BA7]'
                : 'text-zinc-500 hover:text-zinc-900 hover:bg-[#D9F0F7]'
            )
          }
        >
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}
