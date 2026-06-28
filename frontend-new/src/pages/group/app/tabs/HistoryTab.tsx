import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { IconHistory, IconRotateClockwise } from '@tabler/icons-react';
import { useAppDetail } from '@/layouts/AppDetailLayout';
import { appsApi } from '@/api/apps';
import { AppHistoryEntry } from '@/types';
import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from '@/components/ui/toast';
import { cn } from '@/utils/cn';

function shortSha(revisions: string[]): string {
  return revisions[0]?.slice(0, 8) ?? '—';
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString('fr-FR', {
    day: '2-digit', month: '2-digit', year: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
}

function initiatorLabel(entry: AppHistoryEntry): string {
  if (entry.initiatedBy?.username) return entry.initiatedBy.username;
  if (entry.initiatedBy?.automated) return 'auto-sync';
  return '—';
}

interface EntryRowProps {
  entry: AppHistoryEntry;
  isLatest: boolean;
  env: 'dev' | 'prod';
  appId: number;
}

function EntryRow({ entry, isLatest, env, appId }: EntryRowProps) {
  const [confirming, setConfirming] = useState(false);
  const queryClient = useQueryClient();

  const { mutate: doRollback, isPending } = useMutation({
    mutationFn: () => appsApi.rollback(appId, entry.id, env),
    onSuccess: () => {
      toast({ title: `Rollback ${env} started`, description: `Revision ${shortSha(entry.revisions)} is being deployed.` });
      setConfirming(false);
      queryClient.invalidateQueries({ queryKey: ['app-status', appId] });
    },
    onError: (err: Error) => {
      toast({ title: 'Rollback failed', description: err.message, variant: 'destructive' });
      setConfirming(false);
    },
  });

  return (
    <div className={cn(
      'flex items-center gap-4 px-4 py-3 text-sm border-b border-border last:border-0 bg-background hover:bg-muted/40 transition-colors',
      isLatest && 'bg-primary/5 hover:bg-primary/10'
    )}>
      <code className="w-20 font-mono text-xs text-muted-foreground shrink-0">
        {shortSha(entry.revisions)}
      </code>
      <span className="flex-1 text-muted-foreground">{formatDate(entry.deployedAt)}</span>
      <span className="w-28 text-muted-foreground truncate">{initiatorLabel(entry)}</span>
      {isLatest ? (
        <span className="text-xs font-medium text-primary w-24 text-right">current</span>
      ) : (
        <div className="flex gap-1.5 w-24 justify-end">
          {confirming ? (
            <>
              <Button size="sm" variant="danger" onClick={() => doRollback()} disabled={isPending}>
                {isPending ? <Spinner size="sm" /> : 'Confirm'}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setConfirming(false)} disabled={isPending}>
                ✕
              </Button>
            </>
          ) : (
            <Button size="sm" variant="secondary" icon={<IconRotateClockwise size={13} />} onClick={() => setConfirming(true)}>
              Rollback
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

interface EnvSectionProps {
  label: string;
  entries: AppHistoryEntry[];
  env: 'dev' | 'prod';
  appId: number;
  isLoading: boolean;
}

function EnvSection({ label, entries, env, appId, isLoading }: EnvSectionProps) {
  return (
    <div className="rounded-lg border border-border overflow-hidden bg-background">
      <div className="flex items-center gap-2 px-4 py-2.5 bg-background-subtle border-b border-border">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">{label}</span>
        {!isLoading && (
          <span className="text-xs text-muted-foreground">· {entries.length} {entries.length !== 1 ? 'entries' : 'entry'}</span>
        )}
      </div>
      {isLoading ? (
        <div className="p-4 space-y-2">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      ) : entries.length === 0 ? (
        <div className="px-4 py-6 text-sm text-muted-foreground text-center">No deployments recorded.</div>
      ) : (
        <div>
          {[...entries].reverse().map((entry, i) => (
            <EntryRow
              key={entry.id}
              entry={entry}
              isLatest={i === 0}
              env={env}
              appId={appId}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function HistoryTab() {
  const { app } = useAppDetail();

  const { data, isLoading } = useQuery({
    queryKey: ['app-history', app?.id],
    queryFn: () => appsApi.getHistory(app!.id),
    enabled: !!app?.id,
    staleTime: 30_000,
  });

  if (!app) return null;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <IconHistory size={16} className="text-muted-foreground" />
        <h2 className="text-sm font-semibold">Deployment history</h2>
      </div>

      <EnvSection
        label="Production"
        entries={data?.prod ?? []}
        env="prod"
        appId={app.id}
        isLoading={isLoading}
      />
      <EnvSection
        label="Development"
        entries={data?.dev ?? []}
        env="dev"
        appId={app.id}
        isLoading={isLoading}
      />
    </div>
  );
}
