import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  IconCircleCheck,
  IconCircleX,
  IconLoader2,
  IconChevronDown,
  IconChevronUp,
  IconBrandGitlab,
  IconExternalLink,
  IconGitBranch,
} from '@tabler/icons-react';
import { useAppDetail } from '@/layouts/AppDetailLayout';
import { appsApi } from '@/api/apps';
import { Deployment, DeploymentStatus } from '@/types';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
import { timeAgo, formatDuration } from '@/utils/timeAgo';
import { cn } from '@/utils/cn';
import { appUrl } from '@/utils/appUrls';

function StatusIcon({ status }: { status: DeploymentStatus }) {
  if (status === 'succeeded') return <IconCircleCheck size={16} className="text-success-text" />;
  if (status === 'failed') return <IconCircleX size={16} className="text-danger-text" />;
  return <IconLoader2 size={16} className="text-muted-foreground animate-spin" />;
}

// MOCK: commitMessage, branch, duration, author, imageTag sont générés côté client
// décommissionner quand ces champs sont stockés en DB et renvoyés par GET /deployments/
// gitlabPipelineUrl est dérivé de app.source_url + deployment.version (commit hash)
function enrichDeployment(d: Deployment, index: number, repoUrl?: string | null) {
  const commitHash = d.version.slice(0, 8);
  const gitlabPipelineUrl = repoUrl
    ? `${repoUrl.replace(/\/$/, '')}/-/pipelines?sha=${d.version}`
    : null;
  return {
    ...d,
    commitHash,
    commitMessage: index === 0 ? 'feat: add user authentication' : `chore: bump version to ${d.version.slice(0, 6)}`,
    branch: 'main',
    duration: 95 + index * 12,
    author: 'alice.martin',
    imageTag: `registry.cnp.internal/app:${commitHash}`,
    gitlabPipelineUrl,
    isCurrent: index === 0 && d.status === 'succeeded',
  };
}

export function DeploymentsTab() {
  const { app } = useAppDetail();
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const { data: deployments = [], isLoading } = useQuery({
    queryKey: ['deployments', app?.id],
    queryFn: () => appsApi.listDeployments(app!.id),
    enabled: !!app,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Spinner size="lg" />
      </div>
    );
  }

  const enriched = deployments.map((d, i) => enrichDeployment(d, i, app?.repo_url ?? app?.source_url));

  return (
    <div className="bg-card border border-border rounded-md divide-y divide-border">
      {enriched.length === 0 && (
        <p className="px-4 py-8 text-sm text-muted-foreground text-center">
          No deployments.
        </p>
      )}
      {enriched.map((d) => {
        const isExpanded = expandedId === d.id;
        return (
          <div key={d.id}>
            <button
              className="w-full flex items-center gap-3 px-4 py-3 hover:bg-accent transition-colors text-left"
              onClick={() => setExpandedId(isExpanded ? null : d.id)}
            >
              <StatusIcon status={d.status} />

              <div className="flex-1 min-w-0 grid grid-cols-3 gap-4 items-center">
                <div>
                  <span className="text-xs font-mono font-medium text-foreground">
                    {d.commitHash}
                  </span>
                  <p className="text-xs text-muted-foreground truncate">{d.commitMessage}</p>
                </div>
                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                  <IconGitBranch size={12} />
                  <span className="font-mono">{d.branch}</span>
                </div>
                <div className="text-xs text-muted-foreground text-right">
                  {timeAgo(d.deployed_at)}
                  {d.duration && (
                    <span className="ml-1 text-muted-foreground/60">
                      · {formatDuration(d.duration)}
                    </span>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-2">
                {d.isCurrent && <Badge variant="primary">current</Badge>}
                {isExpanded ? (
                  <IconChevronUp size={14} className="text-muted-foreground" />
                ) : (
                  <IconChevronDown size={14} className="text-muted-foreground" />
                )}
              </div>
            </button>

            {isExpanded && (() => {
              const isProd = d.branch === 'main';
              const env = isProd ? 'prod' : 'dev' as const;
              const isExposed = isProd ? app?.expose : app?.expose;
              return (
                <div className="bg-background-subtle px-4 py-3 pl-11 border-t border-border">
                  <dl className="flex flex-col gap-1.5 mb-3">
                    {[
                      { label: 'Author', value: d.author },
                      { label: 'Trigger', value: 'commit' },
                      { label: 'Image', value: d.imageTag, mono: true },
                    ].map(({ label, value, mono }) => (
                      <div key={label} className="flex items-baseline gap-2">
                        <dt className="text-xs text-muted-foreground w-16 shrink-0">{label}</dt>
                        <dd className={cn('text-xs text-foreground', mono && 'font-mono')}>
                          {value}
                        </dd>
                      </div>
                    ))}
                    {isExposed && app?.slug && (
                      <div className="flex items-baseline gap-2">
                        <dt className="text-xs text-muted-foreground w-16 shrink-0">URL</dt>
                        <dd className="text-xs">
                          <a
                            href={appUrl(app.slug, env)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-[#007BA7] hover:underline font-mono flex items-center gap-1"
                          >
                            {appUrl(app.slug, env)}
                            <IconExternalLink size={10} />
                          </a>
                        </dd>
                      </div>
                    )}
                  </dl>
                  {d.gitlabPipelineUrl && (
                    <div className="flex justify-end">
                      <Button
                        variant="secondary"
                        size="sm"
                        icon={<IconBrandGitlab size={13} />}
                        onClick={() => window.open(d.gitlabPipelineUrl!, '_blank')}
                      >
                        View pipeline
                        <IconExternalLink size={11} className="ml-1 opacity-60" />
                      </Button>
                    </div>
                  )}
                </div>
              );
            })()}
          </div>
        );
      })}
    </div>
  );
}
