import { useQuery } from '@tanstack/react-query';
import { monitoringApi } from '@/api/monitoring';
import { LogEntry } from '@/types';

interface UseAppLogsOptions {
  appSlug: string;
  namespace?: string;
  level?: string;
  search?: string;
  limit?: number;
}

export function useAppLogs({
  appSlug,
  namespace,
  level,
  search,
  limit = 200,
}: UseAppLogsOptions) {
  return useQuery<LogEntry[]>({
    queryKey: ['logs', appSlug, namespace, level, search, limit],
    queryFn: async () => {
      const entries = await monitoringApi.getLogs({
        app: appSlug,
        namespace,
        level: level !== 'ALL' ? level : undefined,
        limit,
      });
      let result = entries;
      if (level && level !== 'ALL') {
        result = result.filter((e) => e.level === level);
      }
      if (search) {
        const q = search.toLowerCase();
        result = result.filter((e) => e.message.toLowerCase().includes(q));
      }
      return result;
    },
    refetchInterval: 5_000,
    staleTime: 0,
  });
}
