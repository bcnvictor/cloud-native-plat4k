import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { IconAlertTriangle, IconChevronDown, IconChevronRight } from '@tabler/icons-react';
import { useScopeStore } from '@/store/scope';
import { useBreadcrumb } from '@/components/nav/BreadcrumbContext';
import { finopsApi } from '@/api/finops';
import { MetricCard } from '@/components/MetricCard';
import { Card } from '@/components/ui/Card';
import { Select } from '@/components/ui/Select';
import { cn } from '@/utils/cn';

function ProgressBar({ value, max, className }: { value: number; max: number; className?: string }) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div className={cn('h-2 bg-muted rounded-full overflow-hidden', className)}>
      <div className="h-full bg-primary rounded-full" style={{ width: `${pct}%` }} />
    </div>
  );
}

export function FinOps() {
  const { setScope } = useScopeStore();
  const { setBreadcrumb } = useBreadcrumb();
  useEffect(() => { setScope('admin'); }, [setScope]);

  useEffect(() => {
    setBreadcrumb([{ label: 'Platform', to: '/admin/clusters' }, { label: 'FinOps' }]);
    return () => setBreadcrumb([]);
  }, [setBreadcrumb]);

  const [month, setMonth] = useState('2026-06');
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null);

  const { data } = useQuery({
    queryKey: ['finops', month],
    queryFn: () => finopsApi.getData(month),
  });

  if (!data) return null;

  const creditPct = Math.round((data.azureCreditsUsed / data.azureCreditsTotal) * 100);

  return (
    <div className="max-w-[1440px] mx-auto px-8 py-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-foreground">FinOps</h1>
        </div>
        <Select
          options={[
            { value: '2026-06', label: 'June 2026' },
            { value: '2026-05', label: 'May 2026' },
          ]}
          value={month}
          onChange={setMonth}
          className="w-36"
        />
      </div>

      <div className="flex items-start gap-2 rounded-lg border border-warning-border bg-warning-subtle px-4 py-3 mb-6 text-sm text-warning-text">
        <IconAlertTriangle size={16} className="shrink-0 mt-0.5" />
        <p>
          <span className="font-medium">Cluster Oracle (k3s) temporairement non monitoré</span> — les coûts
          affichés couvrent uniquement le cluster AKS. Monitoring multi-cluster planifié (voir roadmap).
        </p>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <MetricCard label="Total cost" value={`$${data.totalCostUsd.toFixed(2)}`} />
        <MetricCard
          label="AKS cost"
          value={`$${data.clusters.find((c) => c.name === 'cnp-aks')?.costUsd.toFixed(2) ?? '—'}`}
        />
        <MetricCard
          label="k3s cost"
          value="$0.00"
          sublabel="Oracle Free Tier"
        />
        <MetricCard
          label="Remaining credits"
          value={`$${(data.azureCreditsTotal - data.azureCreditsUsed).toFixed(0)}`}
          sublabel={`≈ ${data.azureCreditsRemainingDays}d`}
        />
      </div>

      {/* 2-col */}
      <div className="grid grid-cols-2 gap-4">
        {/* Azure credits breakdown */}
        <Card>
          <h2 className="text-sm font-medium text-foreground mb-4">Azure credits</h2>
          <div className="mb-4">
            <div className="flex justify-between text-xs text-muted-foreground mb-1">
              <span>Used</span>
              <span>{creditPct}%</span>
            </div>
            <ProgressBar value={data.azureCreditsUsed} max={data.azureCreditsTotal} />
            <div className="flex justify-between text-xs mt-1">
              <span className="text-foreground">${data.azureCreditsUsed.toFixed(0)}</span>
              <span className="text-muted-foreground">${data.azureCreditsTotal}</span>
            </div>
          </div>

          <h3 className="text-xs text-muted-foreground uppercase tracking-wide mb-3">
            By cluster
          </h3>
          {data.clusters.map((c) => (
            <div key={c.name} className="mb-3">
              <div className="flex justify-between text-xs mb-1">
                <span className="font-mono text-foreground">{c.name}</span>
                <span className="text-muted-foreground">
                  ${c.costUsd.toFixed(2)}
                  {c.costUsd === 0 && (
                    <span className="ml-1 text-success-text">(Free)</span>
                  )}
                </span>
              </div>
              <ProgressBar value={c.costUsd} max={data.totalCostUsd || 1} />
            </div>
          ))}
        </Card>

        {/* Per-group breakdown */}
        <Card padding="none">
          <div className="px-4 py-3 border-b border-border">
            <h2 className="text-sm font-medium text-foreground">By group</h2>
          </div>
          <ul className="divide-y divide-border">
            {data.groups.map((g) => {
              const isExpanded = expandedGroup === g.groupName;
              return (
                <li key={g.groupName}>
                  <button
                    className="w-full flex items-center gap-2 px-4 py-2.5 hover:bg-accent transition-colors text-left"
                    onClick={() => setExpandedGroup(isExpanded ? null : g.groupName)}
                  >
                    {isExpanded ? (
                      <IconChevronDown size={13} className="text-muted-foreground shrink-0" />
                    ) : (
                      <IconChevronRight size={13} className="text-muted-foreground shrink-0" />
                    )}
                    <span className="flex-1 text-sm font-medium text-foreground">
                      {g.groupName}
                    </span>
                    <span className="text-sm text-muted-foreground">
                      ${g.totalUsd.toFixed(2)}
                    </span>
                  </button>

                  {isExpanded && (
                    <ul className="bg-background-subtle border-t border-border pl-8 divide-y divide-border/50">
                      {g.apps.map((a) => (
                        <li
                          key={a.appName}
                          className="flex items-center gap-2 px-4 py-2 text-xs"
                        >
                          <span className="flex-1 text-muted-foreground">{a.appName}</span>
                          <span className="font-medium text-foreground">
                            ${a.costUsd.toFixed(2)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              );
            })}
          </ul>
        </Card>
      </div>
    </div>
  );
}
