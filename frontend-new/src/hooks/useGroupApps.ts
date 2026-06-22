import { useQuery } from '@tanstack/react-query';
import { appsApi } from '@/api/apps';
import { Application } from '@/types';

export function useGroupApps(groupId: number | undefined) {
  return useQuery<Application[]>({
    queryKey: ['apps', 'group', groupId],
    queryFn: async () => {
      const all = await appsApi.list();
      if (groupId === undefined) return [];
      return all.filter((a) => a.owning_gitlab_group_id === groupId);
    },
    enabled: groupId !== undefined,
  });
}
