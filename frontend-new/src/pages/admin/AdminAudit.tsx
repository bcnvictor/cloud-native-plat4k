import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { IconDownload } from '@tabler/icons-react';
import { useScopeStore } from '@/store/scope';
import { useBreadcrumb } from '@/components/nav/BreadcrumbContext';
import { auditApi } from '@/api/audit';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';

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

function humanizeAction(action: string): string {
  const words = action.toLowerCase().replace(/[._]/g, ' ').split(' ');
  return words.map((w, i) => (i === 0 ? w.charAt(0).toUpperCase() + w.slice(1) : w)).join(' ');
}

function formatExtra(extra: Record<string, unknown> | null | undefined): string {
  if (!extra || Object.keys(extra).length === 0) return '—';
  return Object.entries(extra).map(([k, v]) => `${k}=${v}`).join(', ');
}

function toIsoOrUndefined(dateInput: string, endOfDay = false): string | undefined {
  if (!dateInput) return undefined;
  return `${dateInput}T${endOfDay ? '23:59:59' : '00:00:00'}`;
}

export function AdminAudit() {
  const { setScope } = useScopeStore();
  const { setBreadcrumb } = useBreadcrumb();
  useEffect(() => { setScope('admin'); }, [setScope]);

  useEffect(() => {
    setBreadcrumb([{ label: 'Platform', to: '/admin/clusters' }, { label: 'Audit' }]);
    return () => setBreadcrumb([]);
  }, [setBreadcrumb]);

  const [since, setSince] = useState('');
  const [until, setUntil] = useState('');
  const [exporting, setExporting] = useState(false);

  const filters = {
    since: toIsoOrUndefined(since),
    until: toIsoOrUndefined(until, true),
  };

  const { data: logs = [], isLoading } = useQuery({
    queryKey: ['audit-logs', filters.since, filters.until],
    queryFn: () => auditApi.list(100, 0, filters),
  });

  async function handleExport() {
    setExporting(true);
    try {
      const blob = await auditApi.exportCsv(filters);
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `audit-log_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(a.href);
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="max-w-[1440px] mx-auto px-8 py-6">
      <div className="flex items-end justify-between mb-6 flex-wrap gap-4">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Audit log</h1>
          <p className="text-sm text-muted-foreground">{logs.length} entries (last 100)</p>
        </div>

        <div className="flex items-end gap-2">
          <Input
            label="From"
            type="date"
            value={since}
            onChange={(e) => setSince(e.target.value)}
            className="w-36"
          />
          <Input
            label="To"
            type="date"
            value={until}
            onChange={(e) => setUntil(e.target.value)}
            className="w-36"
          />
          <Button
            variant="secondary"
            size="sm"
            icon={<IconDownload size={13} />}
            onClick={handleExport}
            disabled={exporting}
          >
            {exporting ? 'Exporting…' : 'Export CSV'}
          </Button>
        </div>
      </div>

      <div className="bg-card border border-border rounded-md overflow-hidden">
        <div className="grid grid-cols-[1fr_1.2fr_1.2fr_1fr_1.6fr_1fr] gap-4 px-4 py-2 border-b border-border bg-background-subtle">
          {['Timestamp', 'User', 'Action', 'App', 'Details', 'IP'].map((h) => (
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
                className="grid grid-cols-[1fr_1.2fr_1.2fr_1fr_1.6fr_1fr] gap-4 px-4 py-2.5 border-b border-border last:border-0 items-center hover:bg-accent transition-colors"
              >
                <p className="text-xs font-mono text-muted-foreground">{formatDate(log.timestamp)}</p>
                <p className="text-xs text-foreground truncate" title={log.user_email ?? undefined}>
                  {log.user_email ?? (log.user_id ? `user-${log.user_id}` : '—')}
                </p>
                <p className="text-xs text-foreground font-medium truncate">{humanizeAction(log.action)}</p>
                <p className="text-xs font-mono text-muted-foreground truncate">
                  {log.app_name ?? (log.cloud ? `${log.cloud}/${log.resource_id ?? '—'}` : '—')}
                </p>
                <p className="text-xs text-muted-foreground truncate" title={formatExtra(log.extra)}>
                  {formatExtra(log.extra)}
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
