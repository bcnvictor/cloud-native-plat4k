import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { IconCloud, IconServer2 } from '@tabler/icons-react';
import { useScopeStore } from '@/store/scope';
import { useBreadcrumb } from '@/components/nav/BreadcrumbContext';
import { clustersApi } from '@/api/clusters';
import { CLUSTER_METRICS } from '@/mocks/clusterMetrics';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';

export function Clusters() {
  const { setScope } = useScopeStore();
  const { setBreadcrumb } = useBreadcrumb();
  const navigate = useNavigate();
  useEffect(() => { setScope('admin'); }, [setScope]);

  useEffect(() => {
    setBreadcrumb([{ label: 'Platform' }, { label: 'Clusters' }]);
    return () => setBreadcrumb([]);
  }, [setBreadcrumb]);

  const { data: clusters = [], isLoading } = useQuery({
    queryKey: ['clusters'],
    queryFn: clustersApi.list,
  });

  const clusterNames = clusters.length > 0
    ? clusters.map((c) => c.name)
    : Object.keys(CLUSTER_METRICS);

  return (
    <div className="max-w-[1440px] mx-auto px-8 py-6">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-foreground">Clusters</h1>
        <p className="text-sm text-muted-foreground">{clusterNames.length} cluster{clusterNames.length !== 1 ? 's' : ''}</p>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16"><Spinner size="lg" /></div>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          {clusterNames.map((name) => {
            const m = CLUSTER_METRICS[name];
            if (!m) return null;
            const Icon = m.icon === 'cloud' ? IconCloud : IconServer2;
            return (
              <Card key={name} padding="none">
                {/* Header */}
                <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
                  <div className="h-8 w-8 flex items-center justify-center rounded-md bg-background-subtle border border-border">
                    <Icon size={16} className="text-muted-foreground" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium font-mono text-foreground">{name}</p>
                    <p className="text-xs text-muted-foreground">{m.provider} · {m.type}</p>
                  </div>
                  <Badge variant="success" className="border border-success-border gap-1.5">
                    <span className="relative flex h-1.5 w-1.5 shrink-0">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success opacity-60" />
                      <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-success" />
                    </span>
                    Online
                  </Badge>
                </div>

                {/* Metrics */}
                <div className="grid grid-cols-3 gap-0 divide-x divide-border border-b border-border">
                  {[
                    { label: 'Nodes', value: m.nodesActive, pct: undefined },
                    { label: 'CPU',   value: `${m.cpuUsed}/${m.cpuTotal}`, pct: (m.cpuUsed / m.cpuTotal) * 100 },
                    { label: 'RAM',   value: `${m.ramUsedGi}/${m.ramTotalGi} Gi`, pct: (m.ramUsedGi / m.ramTotalGi) * 100 },
                  ].map(({ label, value, pct }) => (
                    <div key={label} className="px-4 py-2.5 text-center">
                      <p className="text-xs text-muted-foreground">{label}</p>
                      <p className="text-sm font-medium text-foreground">{value}</p>
                      {pct !== undefined && (
                        <div className="h-1 w-full bg-muted rounded-full mt-2">
                          <div className="h-1 bg-[#007BA7] rounded-full" style={{ width: `${pct}%` }} />
                        </div>
                      )}
                    </div>
                  ))}
                </div>

                {/* Technical info */}
                <div className="px-4 py-2.5 border-b border-border flex items-center gap-4 text-xs text-muted-foreground">
                  <span>K8s <span className="font-mono text-foreground">{m.k8sVersion}</span></span>
                  <span>{m.type}</span>
                  <span>{m.podsActive} active pods</span>
                </div>

                {/* Namespaces */}
                <div className="px-4 py-3">
                  <p className="text-xs text-muted-foreground uppercase tracking-wide mb-2">Namespaces</p>
                  <ul className="flex flex-col gap-0.5">
                    {m.namespaces.map((ns) => (
                      <li
                        key={ns.name}
                        className="flex items-center gap-2 px-1 py-1 rounded-md hover:bg-accent cursor-pointer transition-colors"
                        onClick={() => navigate(`/admin/apps?namespace=${ns.name}`)}
                      >
                        <span className="text-xs font-mono text-foreground flex-1">{ns.name}</span>
                        <span className="text-xs text-muted-foreground">{ns.apps} apps</span>
                        <span className="text-xs text-muted-foreground">{ns.pods} pods</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
