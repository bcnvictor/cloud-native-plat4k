import { useMemo, useState } from 'react';
import { IconAlertTriangle, IconExternalLink, IconKey, IconPackage, IconShieldCheck, IconTool } from '@tabler/icons-react';
import { useAppDetail } from '@/layouts/AppDetailLayout';
import { useQuery } from '@tanstack/react-query';
import { useSecurityReport } from '@/hooks/useSecurityReport';
import { securityApi } from '@/api/security';
import { assistantApi } from '@/api/assistant';
import { appsApi } from '@/api/apps';
import { apiError } from '@/utils/apiError';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/EmptyState';
import { SecurityFixDialog } from '@/components/SecurityFixDialog';
import { timeAgo } from '@/utils/timeAgo';
import { cn } from '@/utils/cn';
import { SEVERITIES, gradeVariant, severityVariant } from '@/utils/securityGrade';
import type { SecurityFinding, SecuritySeverity, SecurityToolName, SecurityToolReport } from '@/types';

const TOOL_LABEL: Record<SecurityToolName, string> = { trivy: 'Dependencies (CVE)', gitleaks: 'Secrets' };

function StatusBadge({ tool }: { tool?: SecurityToolReport }) {
  if (!tool || tool.status === 'skipped') return <Badge variant="muted">Not run</Badge>;
  if (tool.status === 'failed') return <Badge variant="danger">Scan failed</Badge>;
  return <Badge variant="success">Scanned</Badge>;
}

function ToolCard({ name, tool }: { name: SecurityToolName; tool?: SecurityToolReport }) {
  const Icon = name === 'trivy' ? IconPackage : IconKey;
  const ok = tool?.status === 'ok';
  return (
    <Card>
      <h2 className="text-sm font-medium text-foreground mb-3 flex items-center justify-between">
        <span className="flex items-center gap-1.5"><Icon size={14} className="text-muted-foreground" />{TOOL_LABEL[name]}</span>
        <StatusBadge tool={tool} />
      </h2>
      {!ok ? (
        <p className="text-xs text-muted-foreground flex items-center gap-1.5">
          <IconAlertTriangle size={12} className="shrink-0" />
          {tool?.status === 'failed'
            ? 'The scanner crashed in the last pipeline — this is not a clean result.'
            : 'No result for this scanner in the last pipeline.'}
        </p>
      ) : name === 'trivy' ? (
        <div className="flex flex-wrap gap-1.5">
          {SEVERITIES.filter((s) => (tool.counts[s] ?? 0) > 0).map((s) => (
            <Badge key={s} variant={severityVariant(s)}>{tool.counts[s]} {s.toLowerCase()}</Badge>
          ))}
          {SEVERITIES.every((s) => !(tool.counts[s] ?? 0)) && <Badge variant="success">No vulnerability</Badge>}
        </div>
      ) : (
        <Badge variant={(tool.counts.total ?? 0) > 0 ? 'danger' : 'success'}>
          {(tool.counts.total ?? 0) > 0 ? `${tool.counts.total} secret(s) detected` : 'No secret detected'}
        </Badge>
      )}
    </Card>
  );
}

type Row = SecurityFinding & { tool: SecurityToolName };

export function SecurityTab() {
  const { app } = useAppDetail();
  const { data, isLoading, isError, refetch } = useSecurityReport(app?.id);
  const [toolFilter, setToolFilter] = useState<SecurityToolName | 'all'>('all');
  const [sevFilter, setSevFilter] = useState<SecuritySeverity | 'all'>('all');
  const [fixTarget, setFixTarget] = useState<string | null>(null);
  const { data: ui } = useQuery({ queryKey: ['assistant-ui-settings'], queryFn: assistantApi.getUiSettings, staleTime: 60_000 });
  const { data: myAccess } = useQuery({
    queryKey: ['myAccess', app?.id],
    queryFn: () => appsApi.getMyAccess(app!.id),
    enabled: !!app?.id,
  });
  const canFix = !!myAccess && (myAccess.is_admin || ['developer', 'maintainer', 'owner'].includes(myAccess.tier));

  const rows: Row[] = useMemo(() => {
    const tools = data?.report?.tools ?? {};
    return (['trivy', 'gitleaks'] as SecurityToolName[]).flatMap((t) =>
      (tools[t]?.findings ?? []).map((f) => ({ ...f, tool: t })),
    );
  }, [data]);
  const visible = rows.filter(
    (r) => (toolFilter === 'all' || r.tool === toolFilter) && (sevFilter === 'all' || r.severity === sevFilter),
  );

  function modeBConfig() {
    if (!app || !fixTarget) return {};
    const f = rows.find((r) => r.id === fixTarget);
    if (!ui?.assistant_enabled) return { disabledReason: 'The CNP AI is disabled on this platform. Use the local mode.' };
    if (fixTarget === 'all') return { disabledReason: 'The CNP AI fixes one finding at a time: pick a single finding.' };
    if (f?.tool === 'gitleaks') return { disabledReason: 'Secrets must be revoked and rotated, not patched: use the local mode.' };
    if (!f || !f.fixed_version) return { disabledReason: 'Only dependency vulnerabilities with a published fixed version can be fixed by the CNP AI.' };
    if (!canFix) return { disabledReason: 'You need the developer role on this application to use the CNP AI.' };
    return {
      launch: async () => {
        try {
          return await securityApi.autofix(app.id, f.id);
        } catch (e) {
          throw new Error(apiError(e, 'The AI fix failed, try again later.'));
        }
      },
    };
  }

  if (!app) return null;
  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-20 w-full" />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4"><Skeleton className="h-24" /><Skeleton className="h-24" /></div>
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }
  if (isError || !data) {
    return (
      <Card>
        <div className="flex items-center justify-between">
          <p className="text-sm text-danger-text flex items-center gap-1.5">
            <IconAlertTriangle size={14} /> Could not load the security report.
          </p>
          <Button size="sm" onClick={() => refetch()}>Retry</Button>
        </div>
      </Card>
    );
  }
  if (!data.report) {
    return (
      <EmptyState
        icon={<IconShieldCheck size={40} strokeWidth={1.5} />}
        title="No scan received yet"
        description="Run a pipeline on the default branch: the security report appears here once it completes."
      />
    );
  }

  const { report } = data;
  const tools = report.tools;
  return (
    <div className="space-y-4 pb-24">
      <Card>
        <div className="flex items-center gap-4">
          <Badge variant={gradeVariant(data.grade)} className="text-2xl font-semibold px-4 py-1.5" >
            {data.grade ?? '—'}
          </Badge>
          <div className="flex-1 text-sm">
            <p className="font-medium text-foreground">Security grade</p>
            <p className="text-xs text-muted-foreground">
              {timeAgo(report.received_at)} · <code className="font-mono">{report.commit_sha.slice(0, 8)}</code>
              {data.partial && ' · partial (a scanner did not complete)'}
            </p>
          </div>
          {rows.length > 0 && (
            <Button size="sm" variant="secondary" icon={<IconTool size={13} />} onClick={() => setFixTarget('all')}>
              Fix all
            </Button>
          )}
          <a
            href={/^https?:\/\//i.test(report.pipeline_url) ? report.pipeline_url : undefined}
            target="_blank"
            rel="noreferrer"
            className="text-xs text-primary inline-flex items-center gap-1 hover:underline"
          >
            Pipeline #{report.pipeline_id} <IconExternalLink size={12} />
          </a>
        </div>
      </Card>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <ToolCard name="trivy" tool={tools.trivy} />
        <ToolCard name="gitleaks" tool={tools.gitleaks} />
      </div>

      <div className="rounded-lg border border-border overflow-hidden bg-background">
        <div className="flex flex-wrap items-center gap-2 px-4 py-2.5 bg-background-subtle border-b border-border">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mr-2">Findings</span>
          {(['all', 'trivy', 'gitleaks'] as const).map((t) => (
            <Button key={t} size="sm" variant={toolFilter === t ? 'primary' : 'ghost'} onClick={() => setToolFilter(t)}>
              {t === 'all' ? 'All tools' : TOOL_LABEL[t]}
            </Button>
          ))}
          <span className="w-px h-4 bg-border mx-1" />
          {(['all', ...SEVERITIES.filter((x) => x !== 'UNKNOWN')] as const).map((s) => (
            <Button key={s} size="sm" variant={sevFilter === s ? 'primary' : 'ghost'} onClick={() => setSevFilter(s)}>
              {s === 'all' ? 'All severities' : s.toLowerCase()}
            </Button>
          ))}
        </div>
        {visible.length === 0 ? (
          <div className="px-4 py-6 text-sm text-muted-foreground text-center">No finding matches.</div>
        ) : (
          visible.map((r) => (
            <div
              key={r.id}
              className={cn('flex flex-wrap items-center gap-x-3 gap-y-1 sm:flex-nowrap sm:gap-4 px-4 py-3 text-sm border-b border-border last:border-0 hover:bg-muted/40 transition-colors')}
            >
              <Badge variant={severityVariant(r.severity)} className="order-1 w-20 justify-center shrink-0">{r.severity.toLowerCase()}</Badge>
              <div className="order-4 basis-full sm:order-2 sm:basis-0 flex-1 min-w-0">
                <p className="font-mono text-xs text-foreground truncate">{r.rule}</p>
                <p className="text-xs text-muted-foreground truncate">
                  {r.tool === 'trivy'
                    ? `${r.package} ${r.installed_version}${r.fixed_version ? ` → ${r.fixed_version}` : ' (no fix available)'}`
                    : r.title || 'Secret detected'}
                  {' · '}{r.file}{r.line ? `:${r.line}` : ''}
                </p>
              </div>
              <span className="order-2 ml-auto sm:order-3 sm:ml-0 text-xs text-muted-foreground shrink-0">{r.tool}</span>
              <Button className="order-3 sm:order-4" size="sm" variant="secondary" icon={<IconTool size={13} />} onClick={() => setFixTarget(r.id)}>
                Fix
              </Button>
            </div>
          ))
        )}
        {(tools.trivy?.truncated || tools.gitleaks?.truncated) && (
          <div className="px-4 py-2 text-xs text-muted-foreground border-t border-border">
            List truncated: only the most severe findings are shown. Counts above are exact.
          </div>
        )}
      </div>
      <SecurityFixDialog
        open={fixTarget !== null}
        appId={app.id}
        finding={fixTarget ?? ''}
        onClose={() => setFixTarget(null)}
        modeB={modeBConfig()}
      />
    </div>
  );
}
