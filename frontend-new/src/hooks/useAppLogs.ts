import { useQuery } from '@tanstack/react-query';
import { monitoringApi } from '@/api/monitoring';
import { LogEntry } from '@/types';

interface UseAppLogsOptions {
  appSlug: string;
  level?: string;
  search?: string;
  limit?: number;
}

export function useAppLogs({
  appSlug,
  level,
  search,
  limit = 200,
}: UseAppLogsOptions) {
  return useQuery<LogEntry[]>({
    queryKey: ['logs', appSlug, level, search, limit],
    queryFn: async () => {
      const entries = await monitoringApi.getLogs({
        app: appSlug,
        level: level !== 'ALL' ? level : undefined,
        limit,
      });
      if (search) {
        const q = search.toLowerCase();
        return entries.filter((e) => e.message.toLowerCase().includes(q));
      }
      return entries;
    },
    refetchInterval: 5_000,
    staleTime: 0,
  });
}
