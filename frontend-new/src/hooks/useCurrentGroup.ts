import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { groupsApi } from '@/api/groups';
import { GroupMembership } from '@/types';

export function useCurrentGroup(): GroupMembership | null {
  const { slug } = useParams<{ slug: string }>();

  const { data: groups = [] } = useQuery({
    queryKey: ['my-groups'],
    queryFn: groupsApi.getMyGroups,
    staleTime: 5 * 60 * 1000,
  });

  if (!slug) return null;
  return groupsApi.findBySlug(groups, slug) ?? null;
}
