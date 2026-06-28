import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useScopeStore } from '@/store/scope';
import { useBreadcrumb } from '@/components/nav/BreadcrumbContext';
import { auditApi } from '@/api/audit';
import { Skeleton } from '@/components/ui/skeleton';

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString('en-US', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export function AdminAudit() {
  const { setScope } = useScopeStore();
  const { setBreadcrumb } = useBreadcrumb();
  useEffect(() => { setScope('admin'); }, [setScope]);

  useEffect(() => {
    setBreadcrumb([{ label: 'Platform', to: '/admin/clusters' }, { label: 'Audit' }]);
    return () => setBreadcrumb([]);
  }, [setBreadcrumb]);

  const { data: logs = [], isLoading } = useQuery({
    queryKey: ['audit-logs'],
    queryFn: () => auditApi.list(100, 0),
  });

  return (
    <div className="max-w-[1440px] mx-auto px-8 py-6">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-foreground">Audit log</h1>
        <p className="text-sm text-muted-foreground">{logs.length} entries (last 100)</p>
      </div>

      <div className="bg-card border border-border rounded-md overflow-hidden">
        <div className="grid grid-cols-[1fr_1fr_2fr_1fr_1fr] gap-4 px-4 py-2 border-b border-border bg-background-subtle">
          {['Timestamp', 'User', 'Action', 'Resource', 'IP'].map((h) => (
            <p key={h} className="text-xs font-medium text-muted-foreground">{h}</p>
          ))}
        </div>

        {isLoading
          ? Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="px-4 py-3 border-b border-border last:border-0">
                <Skeleton className="h-5 w-full rounded" />
              </div>
            ))
          : logs.map((log) => (
              <div
                key={log.id}
                className="grid grid-cols-[1fr_1fr_2fr_1fr_1fr] gap-4 px-4 py-2.5 border-b border-border last:border-0 items-center hover:bg-accent transition-colors"
              >
                <p className="text-xs font-mono text-muted-foreground">{formatDate(log.timestamp)}</p>
                <p className="text-xs text-foreground truncate">{log.user_id ?? '—'}</p>
                <p className="text-xs text-foreground font-medium truncate">{log.action}</p>
                <p className="text-xs font-mono text-muted-foreground truncate">
                  {log.cloud ? `${log.cloud}/` : ''}{log.resource_id ?? '—'}
                </p>
                <p className="text-xs font-mono text-muted-foreground">{log.ip_address ?? '—'}</p>
              </div>
            ))}

        {!isLoading && logs.length === 0 && (
          <p className="px-4 py-8 text-sm text-muted-foreground text-center">
            No audit entries.
          </p>
        )}
      </div>
    </div>
  );
}
