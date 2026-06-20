import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useScopeStore } from '@/store/scope';
import { Breadcrumb } from '@/components/Breadcrumb';
import { auditApi } from '@/api/audit';
import { Skeleton } from '@/components/ui/skeleton';

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString('fr-FR', {
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
  useEffect(() => { setScope('admin'); }, [setScope]);

  const { data: logs = [], isLoading } = useQuery({
    queryKey: ['audit-logs'],
    queryFn: () => auditApi.list(100, 0),
  });

  return (
    <div className="max-w-[1440px] mx-auto px-8 py-6">
      <div className="mb-6">
        <Breadcrumb items={[{ label: 'Plateforme', to: '/admin/clusters' }, { label: 'Audit' }]} />
        <h1 className="text-xl font-semibold text-foreground">Journal d'audit</h1>
        <p className="text-sm text-muted-foreground">{logs.length} entrées (100 dernières)</p>
      </div>

      <div className="bg-card border border-border rounded-md overflow-hidden">
        <div className="grid grid-cols-[1fr_1fr_2fr_1fr_1fr] gap-4 px-4 py-2 border-b border-border bg-background-subtle">
          {['Horodatage', 'Utilisateur', 'Action', 'Ressource', 'IP'].map((h) => (
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
                <p className="text-xs font-mono text-muted-foreground">{formatDate(log.created_at)}</p>
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
            Aucune entrée d'audit.
          </p>
        )}
      </div>
    </div>
  );
}
