import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { IconPencil, IconPlugConnected, IconPlus, IconServer2, IconTrash, IconWifiOff } from '@tabler/icons-react';
import { clustersApi } from '@/api/clusters';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
import { ClusterStatusBadge } from '@/components/ClusterStatusBadge';
import { apiError } from '@/utils/apiError';
import { timeAgo } from '@/utils/timeAgo';
import { cn } from '@/utils/cn';
import type { ClusterConnection, ClusterTestResult } from '@/types';
import { ClusterDrawer } from './ClusterDrawer';
import { DeleteClusterDialog } from './DeleteClusterDialog';
import { TestResultLine } from './TestResultLine';
import { CONFIG_ACTIONS, ConfigHistory } from './ConfigHistory';

const MONITORING: Array<{ key: 'prometheus_url' | 'loki_url' | 'argocd_url'; label: string }> = [
  { key: 'prometheus_url', label: 'Prometheus' },
  { key: 'loki_url', label: 'Loki' },
  { key: 'argocd_url', label: 'ArgoCD' },
];

export function ClusterConnectionsPanel() {
  const qc = useQueryClient();
  const { data: clusters = [], isLoading } = useQuery({ queryKey: ['clusters'], queryFn: clustersApi.list });

  // undefined = fermé, null = création
  const [editing, setEditing] = useState<ClusterConnection | null | undefined>(undefined);
  const [deleting, setDeleting] = useState<ClusterConnection | null>(null);
  const [results, setResults] = useState<Record<number, ClusterTestResult>>({});

  const test = useMutation({
    mutationFn: (id: number) => clustersApi.test(id),
    onSuccess: (result, id) => setResults((r) => ({ ...r, [id]: result })),
    onError: (err, id) =>
      setResults((r) => ({ ...r, [id]: { reachable: false, latency_ms: null, namespace_count: null, error: apiError(err) } })),
    onSettled: () => qc.invalidateQueries({ queryKey: ['audit-logs'] }),
  });

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-foreground">Cluster connections</h2>
          <p className="text-sm text-muted-foreground max-w-prose">
            Kubernetes clusters targeted by deployments. Kubeconfigs and ArgoCD tokens are stored in Vault and never displayed again.
          </p>
        </div>
        <Button variant="primary" icon={<IconPlus size={14} />} onClick={() => setEditing(null)}>
          Add cluster
        </Button>
      </div>

      <Card padding="none" className="hover:translate-y-0 hover:shadow-sm">
        {isLoading ? (
          <div className="flex justify-center py-10"><Spinner size="lg" /></div>
        ) : clusters.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-10 text-center">
            <IconWifiOff size={24} className="text-zinc-300" />
            <p className="text-sm text-muted-foreground">No cluster registered yet</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground border-b border-border">
                  <th className="font-medium px-3 py-2.5">Cluster</th>
                  <th className="font-medium px-3 py-2.5">Status</th>
                  <th className="font-medium px-3 py-2.5 hidden 2xl:table-cell whitespace-nowrap">Last seen</th>
                  <th className="font-medium px-3 py-2.5 hidden md:table-cell">Apps</th>
                  <th className="font-medium px-3 py-2.5 hidden 2xl:table-cell">Monitoring</th>
                  <th className="px-3 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {clusters.map((c) => {
                  const testing = test.isPending && test.variables === c.id;
                  return (
                    <tr key={c.id} className="hover:bg-background-subtle">
                      <td className="px-3 py-3">
                        <div className="flex items-center gap-2.5 min-w-0">
                          <div className="h-8 w-8 shrink-0 flex items-center justify-center rounded-md bg-background-subtle border border-border">
                            <IconServer2 size={15} className="text-muted-foreground" />
                          </div>
                          <div className="min-w-0 max-w-[16rem]">
                            <p className="font-mono font-medium text-foreground">{c.name}</p>
                            <p className="text-xs font-mono text-muted-foreground truncate max-w-[16rem]">{c.endpoint}</p>
                            {testing && <p className="text-xs text-muted-foreground">Testing…</p>}
                            {!testing && results[c.id] && <TestResultLine result={results[c.id]} />}
                          </div>
                        </div>
                      </td>
                      <td className="px-3 py-3"><ClusterStatusBadge status={c.status} /></td>
                      <td className="px-3 py-3 text-xs text-muted-foreground hidden 2xl:table-cell whitespace-nowrap">
                        {c.last_seen_at ? timeAgo(c.last_seen_at) : 'never'}
                      </td>
                      <td className="px-3 py-3 tabular-nums hidden md:table-cell">{c.app_count}</td>
                      <td className="px-3 py-3 hidden 2xl:table-cell">
                        <div className="flex flex-wrap gap-1.5">
                          {MONITORING.map(({ key, label }) => (
                            <span
                              key={key}
                              className={cn(
                                'text-[11px] px-1.5 py-px rounded border border-border text-muted-foreground',
                                !c[key] && 'border-dashed opacity-60'
                              )}
                            >
                              {label}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="px-3 py-3">
                        <div className="flex justify-end gap-1">
                          <Button size="sm" variant="ghost" title="Test connection" aria-label={`Test ${c.name}`} loading={testing} onClick={() => test.mutate(c.id)}>
                            {!testing && <IconPlugConnected size={14} />}
                          </Button>
                          <Button size="sm" variant="ghost" title="Edit" aria-label={`Edit ${c.name}`} onClick={() => setEditing(c)}>
                            <IconPencil size={14} />
                          </Button>
                          <Button size="sm" variant="ghost" title="Delete" aria-label={`Delete ${c.name}`} onClick={() => setDeleting(c)}>
                            <IconTrash size={14} />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <ConfigHistory title="Change history" actions={CONFIG_ACTIONS.clusters} />

      {editing !== undefined && <ClusterDrawer cluster={editing} onClose={() => setEditing(undefined)} />}
      {deleting && <DeleteClusterDialog cluster={deleting} onClose={() => setDeleting(null)} />}
    </div>
  );
}
