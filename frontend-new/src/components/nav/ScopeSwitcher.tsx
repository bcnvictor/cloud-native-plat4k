import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  IconChevronDown,
  IconLayoutGrid,
  IconServer,
} from '@tabler/icons-react';
import { groupsApi } from '@/api/groups';
import { useAuthStore } from '@/store/auth';
import { useScopeStore } from '@/store/scope';
import { Dropdown, DropdownItem } from '@/components/ui/Dropdown';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/utils/cn';

interface ScopeSwitcherProps {
  collapsed?: boolean;
}

export function ScopeSwitcher({ collapsed = false }: ScopeSwitcherProps) {
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const { activeScope, activeGroupSlug } = useScopeStore();

  const { data: groups = [] } = useQuery({
    queryKey: ['my-groups'],
    queryFn: groupsApi.getMyGroups,
    staleTime: 5 * 60 * 1000,
  });

  const activeGroup = groups.find(
    (g) => groupsApi.getSlug(g) === activeGroupSlug
  );

  if (collapsed) {
    return (
      <div className="flex justify-center py-2">
        <IconLayoutGrid size={18} className="text-muted-foreground" />
      </div>
    );
  }

  const items: DropdownItem[] = [
    ...groups.map((g) => {
      const slug = groupsApi.getSlug(g);
      return {
        key: `group-${g.gitlab_group_id}`,
        label: g.name,
        active: activeScope === 'group' && slug === activeGroupSlug,
        onClick: () => navigate(`/groups/${slug}`),
      };
    }),
    ...(user?.is_admin
      ? [
          {
            key: '__divider__',
            label: (
              <span className="text-xs text-muted-foreground uppercase tracking-wide px-0">
                Administration
              </span>
            ),
            divider: true,
            disabled: true,
          },
          {
            key: 'platform',
            label: (
              <span className="flex items-center gap-2">
                Platform
                <Badge variant="primary">admin</Badge>
              </span>
            ),
            icon: <IconServer size={14} className="text-primary" />,
            active: activeScope === 'admin',
            onClick: () => navigate('/admin/clusters'),
          },
        ]
      : []),
  ];

  const isSingleGroup = groups.length <= 1 && !user?.is_admin;

  const triggerContent =
    activeScope === 'admin' ? (
      <div className="flex flex-col min-w-0">
        <div className="flex items-center gap-2">
          <IconServer size={15} className="text-primary shrink-0" />
          <span className="text-sm font-semibold text-foreground">Platform</span>
          <Badge variant="primary">admin</Badge>
        </div>
      </div>
    ) : activeGroup ? (
      <div className="flex flex-col min-w-0">
        <span className="text-sm font-semibold text-foreground truncate">
          {activeGroup.name}
        </span>
        <span className="text-xs text-muted-foreground">
          {groups.length} group{groups.length > 1 ? 's' : ''}
        </span>
      </div>
    ) : (
      <span className="text-sm text-muted-foreground">Sélectionner un groupe</span>
    );

  if (isSingleGroup) {
    return (
      <div className="px-3 py-2.5">
        {triggerContent}
      </div>
    );
  }

  return (
    <Dropdown
      trigger={
        <button
          className={cn(
            'w-full flex items-center gap-2 px-3 py-2.5 rounded-md transition-colors',
            'hover:bg-accent text-foreground text-left'
          )}
        >
          <div className="flex-1 min-w-0">
            {triggerContent}
          </div>
          <IconChevronDown size={14} className="text-muted-foreground shrink-0" />
        </button>
      }
      items={items}
      align="left"
      width={220}
    />
  );
}
