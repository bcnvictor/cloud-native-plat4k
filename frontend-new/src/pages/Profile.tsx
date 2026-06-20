import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  IconKey,
  IconCopy,
  IconTrash,
  IconCheck,
  IconRefresh,
} from '@tabler/icons-react';
import { useAuthStore } from '@/store/auth';
import { authApi } from '@/api/auth';
import { groupsApi } from '@/api/groups';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Badge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import { useToast } from '@/components/ui/toast';
import { timeAgo } from '@/utils/timeAgo';

export function Profile() {
  const { user } = useAuthStore();
  const qc = useQueryClient();
  const { toast } = useToast();

  const [newKeyLabel, setNewKeyLabel] = useState('');
  const [revealedKey, setRevealedKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const { data: groups = [], isLoading: groupsLoading } = useQuery({
    queryKey: ['my-groups'],
    queryFn: groupsApi.getMyGroups,
    staleTime: 5 * 60 * 1000,
  });

  const { data: apiKeys = [], isLoading: keysLoading } = useQuery({
    queryKey: ['api-keys'],
    queryFn: authApi.listApiKeys,
  });

  const syncMutation = useMutation({
    mutationFn: groupsApi.syncTeams,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['my-groups'] });
      toast({ title: 'Synchronisation effectuée' });
    },
  });

  const createKeyMutation = useMutation({
    mutationFn: () => authApi.createApiKey(newKeyLabel),
    onSuccess: (data) => {
      setNewKeyLabel('');
      setRevealedKey(data.key);
      qc.invalidateQueries({ queryKey: ['api-keys'] });
    },
  });

  const deleteKeyMutation = useMutation({
    mutationFn: authApi.deleteApiKey,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['api-keys'] }),
  });

  async function copyKey(key: string) {
    await navigator.clipboard.writeText(key);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const TIER_LABELS: Record<string, string> = {
    viewer: 'Viewer',
    developer: 'Developer',
    maintainer: 'Maintainer',
    owner: 'Owner',
  };

  if (!user) return null;

  return (
    <div className="max-w-[1440px] mx-auto px-8 py-6">
      <h1 className="text-xl font-semibold text-foreground mb-6">Mon profil</h1>
      <div className="max-w-2xl flex flex-col gap-6">

        {/* Identity */}
        <Card>
          <h2 className="text-sm font-medium text-foreground mb-4">Identité</h2>
          <dl className="flex flex-col gap-2">
            {[
              { label: 'Email', value: user.email },
              { label: 'Rôle', value: user.role },
              { label: 'Admin', value: user.is_admin ? 'Oui' : 'Non' },
              { label: 'GitLab ID', value: user.gitlab_user_id ? String(user.gitlab_user_id) : '—' },
              { label: 'Membre depuis', value: timeAgo(user.created_at) },
            ].map(({ label, value }) => (
              <div key={label} className="flex items-baseline gap-2">
                <dt className="text-xs text-muted-foreground w-28 shrink-0">{label}</dt>
                <dd className="text-xs text-foreground">{value}</dd>
              </div>
            ))}
          </dl>
        </Card>

        {/* Groups */}
        <Card>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-medium text-foreground">Mes groupes GitLab</h2>
            <Button
              variant="secondary"
              size="sm"
              icon={<IconRefresh size={13} />}
              loading={syncMutation.isPending}
              onClick={() => syncMutation.mutate()}
            >
              Sync teams
            </Button>
          </div>
          {groupsLoading ? (
            <Spinner size="sm" />
          ) : groups.length === 0 ? (
            <p className="text-xs text-muted-foreground">Aucun groupe.</p>
          ) : (
            <ul className="divide-y divide-border">
              {groups.map((g) => (
                <li key={g.gitlab_group_id} className="flex items-center gap-3 py-2">
                  <span className="flex-1 text-xs text-foreground">{g.name}</span>
                  <span className="text-xs text-muted-foreground font-mono">{g.full_path}</span>
                  <Badge variant="muted">{TIER_LABELS[g.tier_cnp] ?? g.tier_cnp}</Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* API Keys */}
        <Card>
          <h2 className="text-sm font-medium text-foreground mb-4">Clés API</h2>

          {revealedKey && (
            <div className="mb-4 p-3 bg-background-subtle border border-border rounded-md">
              <p className="text-xs text-muted-foreground mb-2">
                Copiez cette clé maintenant — elle ne sera plus affichée.
              </p>
              <div className="flex items-center gap-2">
                <code className="flex-1 text-xs font-mono text-foreground break-all">{revealedKey}</code>
                <button
                  onClick={() => copyKey(revealedKey)}
                  className="text-muted-foreground hover:text-foreground transition-colors shrink-0"
                >
                  {copied ? <IconCheck size={14} className="text-success-text" /> : <IconCopy size={14} />}
                </button>
              </div>
            </div>
          )}

          <div className="flex gap-2 mb-4">
            <Input
              placeholder="Label (ex: CI pipeline)"
              value={newKeyLabel}
              onChange={(e) => setNewKeyLabel(e.target.value)}
              className="flex-1"
            />
            <Button
              variant="primary"
              size="sm"
              icon={<IconKey size={13} />}
              loading={createKeyMutation.isPending}
              disabled={!newKeyLabel.trim()}
              onClick={() => createKeyMutation.mutate()}
            >
              Générer
            </Button>
          </div>

          {keysLoading ? (
            <Spinner size="sm" />
          ) : apiKeys.length === 0 ? (
            <p className="text-xs text-muted-foreground">Aucune clé active.</p>
          ) : (
            <ul className="divide-y divide-border">
              {apiKeys.map((k) => (
                <li key={k.id} className="flex items-center gap-3 py-2.5">
                  <IconKey size={14} className="text-muted-foreground shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-foreground">{k.label}</p>
                    <p className="text-xs text-muted-foreground font-mono">
                      {k.key_prefix}••••••••
                      {k.last_used_at && ` · utilisée ${timeAgo(k.last_used_at)}`}
                    </p>
                  </div>
                  <span className="text-xs text-muted-foreground shrink-0">{timeAgo(k.created_at)}</span>
                  <button
                    onClick={() => deleteKeyMutation.mutate(k.id)}
                    className="text-muted-foreground hover:text-danger transition-colors"
                  >
                    <IconTrash size={14} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
