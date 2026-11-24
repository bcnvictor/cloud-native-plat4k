import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { IconClock, IconExternalLink, IconGitBranch, IconPlus, IconStack2, IconTrash } from '@tabler/icons-react';
import { appsApi } from '@/api/apps';
import { ephemeralEnvsApi } from '@/api/ephemeralEnvs';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Select } from '@/components/ui/Select';
import { Spinner } from '@/components/ui/Spinner';
import { toast } from '@/components/ui/toast';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { EmptyState } from '@/components/EmptyState';
import { EphemeralEnv } from '@/types';
import { apiError } from '@/utils/apiError';
import { EPHEMERAL_STATUS, TTL_OPTIONS, canManageEphemeral, showUrl, ttlRemaining } from '@/utils/ephemeralEnv';
import { useAppDetail } from '@/layouts/AppDetailLayout';

/** Environnements éphémères d'une app (ADR-0030, 4K-289) : un env par branche, avec sa
 *  propre URL, détruit à l'expiration de son TTL ou à la demande. */
export function EnvironmentsTab() {
  const { app } = useAppDetail();
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [toDestroy, setToDestroy] = useState<EphemeralEnv | null>(null);

  const { data: myAccess } = useQuery({
    queryKey: ['myAccess', app?.id],
    queryFn: () => appsApi.getMyAccess(app!.id),
    enabled: !!app?.id,
  });
  const canManage = canManageEphemeral(myAccess);

  const { data: envs, isLoading, error } = useQuery({
    queryKey: ['ephemeral-envs', app?.id],
    queryFn: () => ephemeralEnvsApi.list(app!.id),
    enabled: !!app?.id,
    // Plus fréquent tant qu'un env change d'état (build, certificat, purge)
    refetchInterval: (query) =>
      query.state.data?.some((e) => e.status === 'provisioning' || e.status === 'destroying') ? 10_000 : 30_000,
  });

  const destroy = useMutation({
    mutationFn: (env: EphemeralEnv) => ephemeralEnvsApi.destroy(app!.id, env.id),
    onSuccess: (env) => {
      toast({
        title: env.status === 'destroyed' ? 'Environment destroyed' : 'Destruction started',
        description:
          env.status === 'destroyed' ? env.name : `${env.name} disappears once ArgoCD has removed its namespace.`,
      });
      queryClient.invalidateQueries({ queryKey: ['ephemeral-envs', app?.id] });
    },
    onError: (e) => toast({ title: 'Destruction failed', description: apiError(e), variant: 'destructive' }),
    onSettled: () => setToDestroy(null),
  });

  if (!app) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <IconStack2 size={16} className="text-muted-foreground" />
            Ephemeral environments
          </h2>
          <p className="text-xs text-muted-foreground mt-1 max-w-xl">
            Deploy a branch in its own namespace with its own HTTPS URL. It reuses the dev variables and is
            destroyed when its time to live expires.
          </p>
        </div>
        {canManage && !creating && (
          <Button variant="primary" size="sm" icon={<IconPlus size={14} />} onClick={() => setCreating(true)}>
            New environment
          </Button>
        )}
      </div>

      {creating && (
        <CreateEnvForm
          appId={app.id}
          onDone={() => {
            setCreating(false);
            queryClient.invalidateQueries({ queryKey: ['ephemeral-envs', app.id] });
          }}
          onCancel={() => setCreating(false)}
        />
      )}

      {isLoading ? (
        <div className="flex justify-center py-10">
          <Spinner />
        </div>
      ) : error ? (
        <Card>
          <p className="text-sm text-danger-text">{apiError(error, 'Could not load the environments')}</p>
        </Card>
      ) : !envs?.length ? (
        <Card padding="none">
          <EmptyState
            icon={<IconGitBranch size={36} strokeWidth={1.5} />}
            title="No ephemeral environment"
            description={canManage ? 'Create one from a branch to preview it before merging.' : undefined}
          />
        </Card>
      ) : (
        <Card padding="none" className="divide-y divide-border">
          {envs.map((env) => (
            <EnvRow key={env.id} env={env} canManage={canManage} onDestroy={() => setToDestroy(env)} />
          ))}
        </Card>
      )}

      <ConfirmDialog
        open={!!toDestroy}
        title={`Destroy ${toDestroy?.name ?? ''}?`}
        description={`The namespace of branch "${toDestroy?.branch ?? ''}" and everything in it will be deleted. dev, prod and the repository are not affected.`}
        confirmLabel="Destroy"
        loading={destroy.isPending}
        onConfirm={() => toDestroy && destroy.mutate(toDestroy)}
        onCancel={() => setToDestroy(null)}
      />
    </div>
  );
}

function EnvRow({ env, canManage, onDestroy }: { env: EphemeralEnv; canManage: boolean; onDestroy: () => void }) {
  const status = EPHEMERAL_STATUS[env.status];
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3" data-testid={`ephemeral-env-${env.slug}`}>
      <div className="min-w-[220px] flex-1">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm text-foreground">{env.name}</span>
          <Badge variant={status.variant}>{status.label}</Badge>
        </div>
        <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <IconGitBranch size={13} />
            {env.branch}
          </span>
          {env.image_tag && <span className="font-mono">{env.image_tag}</span>}
          <span>{env.cluster_name}</span>
        </div>
      </div>

      <div className="min-w-[260px] text-sm">
        {env.url && showUrl(env.status) ? (
          <a
            href={env.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-[#007BA7] hover:underline"
          >
            <IconExternalLink size={14} />
            <span className="font-mono truncate">{env.url.replace('https://', '')}</span>
          </a>
        ) : (
          <span className="text-xs text-muted-foreground">
            {env.status === 'provisioning'
              ? 'URL available once the branch is built and its certificate issued'
              : env.status === 'failed'
                ? 'The pipeline failed: push a fix to the branch to retry'
                : '—'}
          </span>
        )}
      </div>

      <div className="flex items-center gap-1 text-xs text-muted-foreground w-24" title={env.expires_at}>
        <IconClock size={13} />
        {env.status === 'destroying' ? 'destroying' : ttlRemaining(env.expires_at)}
      </div>

      {canManage && (
        <Button
          variant="ghost"
          size="sm"
          icon={<IconTrash size={14} />}
          onClick={onDestroy}
          disabled={env.status === 'destroying'}
          aria-label={`Destroy ${env.name}`}
        >
          Destroy
        </Button>
      )}
    </div>
  );
}

function CreateEnvForm({ appId, onDone, onCancel }: { appId: number; onDone: () => void; onCancel: () => void }) {
  const [branch, setBranch] = useState('');
  const [ttl, setTtl] = useState('24');

  const { data: branches, isLoading, error } = useQuery({
    queryKey: ['ephemeral-branches', appId],
    queryFn: () => ephemeralEnvsApi.branches(appId),
  });

  const create = useMutation({
    mutationFn: () => ephemeralEnvsApi.create(appId, branch, Number(ttl)),
    onSuccess: (env) => {
      toast({ title: 'Environment requested', description: `${env.name}: building branch ${env.branch}.` });
      onDone();
    },
  });

  return (
    <Card className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-[2fr_1fr]">
        {isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Spinner /> Loading branches…
          </div>
        ) : (
          <Select
            label="Branch"
            value={branch}
            onChange={setBranch}
            placeholder={branches?.length ? 'Choose a branch' : 'No branch other than the default one'}
            options={(branches ?? []).map((b) => ({ value: b, label: b }))}
            disabled={!branches?.length}
            hint={error ? apiError(error, 'Could not list the branches') : undefined}
          />
        )}
        <Select label="Time to live" value={ttl} onChange={setTtl} options={TTL_OPTIONS} />
      </div>
      {create.error && (
        <p className="text-xs text-danger-text" role="alert">
          {apiError(create.error, 'Could not create the environment')}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={onCancel} disabled={create.isPending}>
          Cancel
        </Button>
        <Button variant="primary" size="sm" onClick={() => create.mutate()} disabled={!branch} loading={create.isPending}>
          Create
        </Button>
      </div>
    </Card>
  );
}
