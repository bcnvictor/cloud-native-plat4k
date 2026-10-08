import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { IconPlus, IconRefresh, IconTrash } from '@tabler/icons-react';
import { adminApi } from '@/api/admin';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Spinner } from '@/components/ui/Spinner';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { toast } from '@/components/ui/toast';
import { apiError } from '@/utils/apiError';
import { timeAgo } from '@/utils/timeAgo';
import type { GitLabGroupAdmin } from '@/types';
import { CONFIG_ACTIONS, ConfigHistory } from './ConfigHistory';

export function GitLabGroupsPanel() {
  const qc = useQueryClient();
  const { data: groups = [], isLoading } = useQuery({
    queryKey: ['admin-gitlab-groups'],
    queryFn: adminApi.listGitlabGroups,
  });
  const [identifier, setIdentifier] = useState('');
  const [removing, setRemoving] = useState<GitLabGroupAdmin | null>(null);

  function refresh() {
    qc.invalidateQueries({ queryKey: ['admin-gitlab-groups'] });
    qc.invalidateQueries({ queryKey: ['audit-logs'] });
  }

  const register = useMutation({
    mutationFn: () => adminApi.registerGitlabGroup(identifier.trim()),
    onSuccess: (group) => {
      setIdentifier('');
      refresh();
      toast({ title: `${group.full_path} registered` });
    },
    onError: (err) => toast({ title: 'Registration failed', description: apiError(err), variant: 'destructive' }),
  });

  const deregister = useMutation({
    mutationFn: (group: GitLabGroupAdmin) => adminApi.deregisterGitlabGroup(group.gitlab_group_id),
    onSuccess: (_, group) => {
      setRemoving(null);
      refresh();
      toast({ title: `${group.full_path} removed` });
    },
    onError: (err) => toast({ title: 'Removal failed', description: apiError(err), variant: 'destructive' }),
  });

  const sync = useMutation({
    mutationFn: adminApi.syncGitlab,
    onSuccess: (result) => {
      refresh();
      if (result.skipped) {
        toast({ title: 'Sync skipped', description: 'GitLab is not configured on the server (GITLAB_BOT_TOKEN).', variant: 'destructive' });
      } else {
        const g = result.groups;
        toast({ title: 'Sync complete', description: g ? `Groups: ${g.created} created, ${g.updated} updated, ${g.revoked} revoked` : undefined });
      }
    },
    onError: (err) => toast({ title: 'Sync failed', description: apiError(err), variant: 'destructive' }),
  });

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-foreground">GitLab groups</h2>
          <p className="text-sm text-muted-foreground max-w-prose">
            Groups whose members are mirrored into the CNP. The service account is configured on the server
            (<span className="font-mono">GITLAB_BOT_TOKEN</span>).
          </p>
        </div>
        <Button icon={<IconRefresh size={14} />} loading={sync.isPending} onClick={() => sync.mutate()}>
          Sync now
        </Button>
      </div>

      <Card padding="none" className="hover:translate-y-0 hover:shadow-sm">
        <form
          className="flex flex-wrap items-end gap-2 px-4 py-3 border-b border-border"
          onSubmit={(e) => {
            e.preventDefault();
            if (identifier.trim()) register.mutate();
          }}
        >
          <div className="flex-1 min-w-[14rem]">
            <Input
              id="gitlab-group-identifier"
              label="Register a group"
              mono
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              placeholder="Group ID or full path (e.g. 4k-cnp-2027/apps)"
            />
          </div>
          <Button type="submit" variant="primary" icon={<IconPlus size={14} />} loading={register.isPending} disabled={!identifier.trim()}>
            Register
          </Button>
        </form>

        {isLoading ? (
          <div className="flex justify-center py-8"><Spinner /></div>
        ) : groups.length === 0 ? (
          <p className="px-4 py-8 text-sm text-muted-foreground text-center">No group registered yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground border-b border-border">
                  <th className="font-medium px-4 py-2.5">Full path</th>
                  <th className="font-medium px-4 py-2.5 hidden md:table-cell">GitLab ID</th>
                  <th className="font-medium px-4 py-2.5">Last sync</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {groups.map((g) => (
                  <tr key={g.gitlab_group_id} className="hover:bg-background-subtle">
                    <td className="px-4 py-2.5 font-mono text-foreground">{g.full_path}</td>
                    <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground tabular-nums hidden md:table-cell">{g.gitlab_group_id}</td>
                    <td className="px-4 py-2.5 text-xs text-muted-foreground">{g.synced_at ? timeAgo(g.synced_at) : 'never'}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex justify-end">
                        <Button size="sm" variant="ghost" aria-label={`Remove ${g.full_path}`} title="Remove" onClick={() => setRemoving(g)}>
                          <IconTrash size={14} />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <ConfigHistory title="Change history" actions={CONFIG_ACTIONS.gitlab} />

      <ConfirmDialog
        open={removing !== null}
        title={`Remove ${removing?.full_path ?? ''}?`}
        description="The group will no longer be synchronized. Members already present in the CNP are kept."
        confirmLabel="Remove"
        loading={deregister.isPending}
        onConfirm={() => removing && deregister.mutate(removing)}
        onCancel={() => setRemoving(null)}
      />
    </div>
  );
}
