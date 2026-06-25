import { useQuery } from '@tanstack/react-query';
import { appsApi } from '@/api/apps';

export function useAppStatus(appId: number | undefined) {
  return useQuery({
    queryKey: ['app-status', appId],
    queryFn: () => appsApi.getStatus(appId!),
    enabled: !!appId,
    refetchInterval: 30_000,
    staleTime: 25_000,
    retry: 1,
  });
}
