import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { IconAlertTriangle, IconInfoCircle, IconPackage } from '@tabler/icons-react';
import { useScopeStore } from '@/store/scope';
import { useBreadcrumb } from '@/components/nav/BreadcrumbContext';
import { useDependencySearch } from '@/hooks/useDependencySearch';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/EmptyState';
import type { DependencyCoverage, DependencyRow } from '@/types';

const PAGE_SIZE = 50;
const ECOSYSTEMS = ['npm', 'pypi', 'golang', 'maven', 'cargo', 'gem'];
const GRID = 'grid grid-cols-[1.3fr_1fr_1.5fr_0.9fr_0.9fr_1.4fr] gap-4 px-4';

function shortDate(iso: string | null): string {
  return iso ? new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit' }) : '—';
}

function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function CoverageBanner({ coverage }: { coverage: DependencyCoverage }) {
  const { apps_total, apps_with_sbom, oldest_snapshot, newest_snapshot } = coverage;
  const partial = apps_with_sbom < apps_total;
  return (
    <Card padding="sm" className={partial ? 'border-warning' : undefined}>
      <p className="text-sm text-foreground flex items-start gap-2" data-testid="coverage-banner">
        {partial ? (
          <IconAlertTriangle size={16} className="shrink-0 mt-0.5 text-warning-text" />
        ) : (
          <IconInfoCircle size={16} className="shrink-0 mt-0.5 text-muted-foreground" />
        )}
        <span>
          <strong>{apps_with_sbom}</strong> of <strong>{apps_total}</strong> apps have an inventory
          {apps_with_sbom > 0 && <> · data from {shortDate(oldest_snapshot)} to {shortDate(newest_snapshot)}</>}
          {partial && <>; the others do not have a recent pipeline yet and are not searched.</>}
        </span>
      </p>
    </Card>
  );
}

function DirectBadge({ direct }: { direct: boolean | null }) {
  if (direct === null) return <Badge variant="muted">Unknown</Badge>;
  return direct ? <Badge variant="info">Direct</Badge> : <Badge variant="muted">Transitive</Badge>;
}

function Row({ r }: { r: DependencyRow }) {
  const securityPath = r.group_slug ? `/groups/${r.group_slug}/apps/${r.app_slug}/security` : null;
  return (
    <div className={`${GRID} py-2.5 border-b border-border last:border-0 items-center hover:bg-accent transition-colors`}>
      <p className="text-sm min-w-0 truncate">
        {securityPath ? (
          <Link to={securityPath} className="text-primary hover:underline" title="Open the Security tab">{r.app_name}</Link>
        ) : (
          <span className="text-foreground">{r.app_name}</span>
        )}
      </p>
      <p className="text-xs text-muted-foreground truncate" title={r.group ?? undefined}>{r.group ?? '—'}</p>
      <p className="text-xs font-mono text-foreground truncate" title={`${r.package} (${r.ecosystem})`}>
        {r.package} <span className="text-muted-foreground">· {r.ecosystem}</span>
      </p>
      <p className="text-xs font-mono text-foreground truncate" title={r.version}>{r.version}</p>
      <div><DirectBadge direct={r.direct} /></div>
      <p className="text-xs text-muted-foreground truncate" title={r.licenses.join(', ')}>
        {r.licenses.length ? r.licenses.join(', ') : '—'}
      </p>
    </div>
  );
}

export function AdminDependencies() {
  const { setScope } = useScopeStore();
  const { setBreadcrumb } = useBreadcrumb();
  useEffect(() => { setScope('admin'); }, [setScope]);
  useEffect(() => {
    setBreadcrumb([{ label: 'Platform', to: '/admin/clusters' }, { label: 'Dependencies' }]);
    return () => setBreadcrumb([]);
  }, [setBreadcrumb]);

  const [q, setQ] = useState('');
  const [version, setVersion] = useState('');
  const [ecosystem, setEcosystem] = useState('');
  const [offset, setOffset] = useState(0);
  const dq = useDebounced(q.trim());
  const dv = useDebounced(version.trim());
  useEffect(() => { setOffset(0); }, [dq, dv, ecosystem]);

  const { data, isLoading, isError, isFetching, refetch } = useDependencySearch({
    q: dq, version: dv, ecosystem, limit: PAGE_SIZE, offset,
  });
  const hasFilter = !!(dq || dv || ecosystem);

  return (
    <div className="max-w-[1440px] mx-auto px-8 py-6 space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-foreground">Dependencies</h1>
        <p className="text-sm text-muted-foreground">
          Which apps use a given package? Search the inventory of the latest default-branch pipeline of every app.
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <Input label="Package" placeholder="e.g. log4j, lodash" value={q} onChange={(e) => setQ(e.target.value)} className="w-64" />
        <Input label="Version" placeholder="exact, e.g. 4.17.20" value={version} onChange={(e) => setVersion(e.target.value)} className="w-44" mono />
        <Select
          label="Ecosystem"
          value={ecosystem}
          onChange={setEcosystem}
          placeholder="All"
          className="w-36"
          options={[{ value: '', label: 'All' }, ...ECOSYSTEMS.map((e) => ({ value: e, label: e }))]}
        />
      </div>

      {data && <CoverageBanner coverage={data.coverage} />}

      <div className="bg-card border border-border rounded-md overflow-hidden">
        <div className="overflow-x-auto">
          <div className="min-w-[860px]">
            <div className={`${GRID} py-2 border-b border-border bg-background-subtle`}>
              {['App', 'Group', 'Package', 'Version', 'Type', 'Licenses'].map((h) => (
                <p key={h} className="text-xs font-medium text-muted-foreground">{h}</p>
              ))}
            </div>

            {isLoading ? (
              Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="px-4 py-3 border-b border-border last:border-0">
                  <Skeleton className="h-5 w-full rounded" />
                </div>
              ))
            ) : isError || !data ? (
              <div className="flex items-center justify-between px-4 py-4">
                <p className="text-sm text-danger-text flex items-center gap-1.5">
                  <IconAlertTriangle size={14} /> Could not load the dependency inventory.
                </p>
                <Button size="sm" onClick={() => refetch()}>Retry</Button>
              </div>
            ) : data.items.length === 0 ? (
              <EmptyState
                icon={<IconPackage size={40} strokeWidth={1.5} />}
                title={data.coverage.apps_with_sbom === 0 ? 'No inventory received yet' : 'No match in the inventory'}
                description={
                  data.coverage.apps_with_sbom === 0
                    ? 'Inventories appear once an app runs a pipeline on its default branch.'
                    : `No inventoried app uses a matching package. This does not cover the ${data.coverage.apps_total - data.coverage.apps_with_sbom} app(s) without an inventory.`
                }
              />
            ) : (
              <div className={isFetching ? 'opacity-60 transition-opacity' : 'transition-opacity'}>
                {data.items.map((r, i) => <Row key={`${r.app_id}-${r.package}-${r.version}-${i}`} r={r} />)}
              </div>
            )}
          </div>
        </div>

        {data && data.total > 0 && (
          <div className="flex items-center justify-between gap-2 px-4 py-2 border-t border-border bg-background-subtle">
            <p className="text-xs text-muted-foreground">
              {offset + 1}–{Math.min(offset + data.items.length, data.total)} of {data.total}
              {hasFilter ? ' matches' : ' components'}
            </p>
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</Button>
              <Button size="sm" variant="secondary" disabled={offset + PAGE_SIZE >= data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</Button>
            </div>
          </div>
        )}
      </div>

      <p className="text-xs text-muted-foreground">
        Limits: the scan reads the repository lockfiles at the root (<code className="font-mono">trivy fs</code>), not the deployed image;
        the inventory comes from the default branch, which may differ from what runs in production; there is no automatic watch —
        an admin has to search.
      </p>
    </div>
  );
}
