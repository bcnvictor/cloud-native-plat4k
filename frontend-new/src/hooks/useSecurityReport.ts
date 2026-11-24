import { useQuery } from '@tanstack/react-query';
import { securityApi } from '@/api/security';

export function useSecurityReport(appId: number | undefined) {
  return useQuery({
    queryKey: ['app-security', appId],
    queryFn: () => securityApi.getLatest(appId!),
    enabled: !!appId,
    staleTime: 60_000,
    retry: 1,
  });
}
