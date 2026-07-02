import { useQuery } from '@tanstack/react-query';
import { appsApi } from '@/api/apps';

export function useAppScaleState(appId: number | undefined) {
  return useQuery({
    queryKey: ['app-scale-state', appId],
    queryFn: () => appsApi.getScaleState(appId!),
    enabled: !!appId,
    refetchInterval: 30_000,
    staleTime: 25_000,
    retry: 1,
  });
}
