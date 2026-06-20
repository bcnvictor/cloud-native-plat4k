import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  IconChevronDown,
  IconServer2,
} from '@tabler/icons-react';
import { groupsApi } from '@/api/groups';
import { useAuthStore } from '@/store/auth';
import { useScopeStore } from '@/store/scope';
import { Dropdown, DropdownItem } from '@/components/ui/Dropdown';
import { Avatar } from '@/components/Avatar';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/cn';

export function ScopeSwitcher() {
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

  const items: DropdownItem[] = [
    ...groups.map((g) => {
      const slug = groupsApi.getSlug(g);
      return {
        key: `group-${g.gitlab_group_id}`,
        label: g.name,
        active: activeScope === 'group' && slug === activeGroupSlug,
        onClick: () => navigate(`/groups/${slug}/apps`),
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
                Plateforme
                <Badge variant="primary">admin</Badge>
              </span>
            ),
            icon: <IconServer2 size={14} />,
            active: activeScope === 'admin',
            onClick: () => navigate('/admin/clusters'),
          },
        ]
      : []),
  ];

  const isSingleGroup = groups.length <= 1 && !user?.is_admin;

  const triggerLabel =
    activeScope === 'admin' ? (
      <span className="flex items-center gap-2">
        <IconServer2 size={16} className="text-muted-foreground shrink-0" />
        <span className="text-sm font-medium">Plateforme</span>
        <Badge variant="primary">admin</Badge>
      </span>
    ) : activeGroup ? (
      <span className="flex items-center gap-2">
        <Avatar name={activeGroup.name} size="sm" shape="rounded" />
        <span className="text-sm font-medium max-w-[120px] truncate">
          {activeGroup.name}
        </span>
      </span>
    ) : (
      <span className="text-sm text-muted-foreground">Sélectionner un groupe</span>
    );

  if (isSingleGroup) {
    return (
      <div className="flex items-center gap-2 px-2 py-1">
        {triggerLabel}
      </div>
    );
  }

  return (
    <Dropdown
      trigger={
        <button
          className={cn(
            'flex items-center gap-1.5 px-2 py-1 rounded-md transition-colors',
            'hover:bg-accent text-foreground'
          )}
        >
          {triggerLabel}
          <IconChevronDown size={14} className="text-muted-foreground shrink-0" />
        </button>
      }
      items={items}
      align="left"
      width={220}
    />
  );
}
