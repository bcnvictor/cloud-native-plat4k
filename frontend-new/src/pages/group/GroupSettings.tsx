import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { IconTrash, IconClock } from '@tabler/icons-react';
import { useCurrentGroup } from '@/hooks/useCurrentGroup';
import { useScopeStore } from '@/store/scope';
import { Breadcrumb } from '@/components/Breadcrumb';
import { appsApi } from '@/api/apps';
import { useGroupApps } from '@/hooks/useGroupApps';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Avatar } from '@/components/Avatar';
import { Badge } from '@/components/ui/Badge';
import { CnpTier } from '@/types';

const TIER_OPTIONS: { value: CnpTier; label: string }[] = [
  { value: 'viewer', label: 'Viewer' },
  { value: 'developer', label: 'Developer' },
  { value: 'maintainer', label: 'Maintainer' },
  { value: 'owner', label: 'Owner' },
];

export function GroupSettings() {
  const { slug } = useParams<{ slug: string }>();
  const group = useCurrentGroup();
  const { setScope } = useScopeStore();
  const qc = useQueryClient();

  useEffect(() => {
    if (slug) setScope('group', slug);
  }, [slug, setScope]);

  const { data: apps = [] } = useGroupApps(group?.gitlab_group_id);
  const firstAppId = apps[0]?.id;

  const { data: members = [] } = useQuery({
    queryKey: ['members', firstAppId],
    queryFn: () => (firstAppId ? appsApi.getMembers(firstAppId) : Promise.resolve([])),
    enabled: !!firstAppId,
  });

  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<CnpTier>('developer');
  const [groupName, setGroupName] = useState(group?.name ?? '');

  useEffect(() => {
    if (group) setGroupName(group.name);
  }, [group]);

  const inviteMutation = useMutation({
    mutationFn: () =>
      firstAppId
        ? appsApi.addMember(firstAppId, { email: inviteEmail, role: inviteRole })
        : Promise.reject('no app'),
    onSuccess: () => {
      setInviteEmail('');
      qc.invalidateQueries({ queryKey: ['members', firstAppId] });
    },
  });

  return (
    <div className="py-6">
      <Breadcrumb items={[{ label: group?.name ?? '…', to: `/groups/${slug}` }, { label: 'Settings' }]} />
      <h1 className="text-xl font-semibold text-foreground mb-6">Settings</h1>
      <div className="max-w-2xl flex flex-col gap-6">

      {/* Identity */}
      <Card>
        <h2 className="text-sm font-medium text-foreground mb-4">Identité</h2>
        <div className="flex gap-3">
          <Input
            label="Nom du groupe"
            value={groupName}
            onChange={(e) => setGroupName(e.target.value)}
            className="flex-1"
          />
          <div className="flex items-end">
            <Button variant="secondary" size="sm" disabled>
              Sauvegarder
            </Button>
          </div>
        </div>
      </Card>

      {/* Members */}
      <Card>
        <h2 className="text-sm font-medium text-foreground mb-4">Membres</h2>

        {/* Invite form */}
        <div className="flex gap-2 mb-5">
          <Input
            placeholder="email ou username GitLab"
            value={inviteEmail}
            onChange={(e) => setInviteEmail(e.target.value)}
            className="flex-1"
          />
          <Select
            options={TIER_OPTIONS}
            value={inviteRole}
            onChange={(v) => setInviteRole(v as CnpTier)}
            className="w-36"
          />
          <Button
            variant="primary"
            size="sm"
            loading={inviteMutation.isPending}
            disabled={!inviteEmail}
            onClick={() => inviteMutation.mutate()}
          >
            Inviter
          </Button>
        </div>

        {/* Member list */}
        <ul className="divide-y divide-border">
          {members
            .filter((m) => m.status === 'active')
            .map((m, i) => {
              const isOwner = m.tier_cnp === 'owner';
              return (
                <li key={i} className="flex items-center gap-3 py-2.5">
                  <Avatar name={m.display_name ?? m.email ?? 'U'} size="md" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">
                      {m.display_name}
                    </p>
                    <p className="text-xs text-muted-foreground truncate">{m.email}</p>
                  </div>
                  <Select
                    options={TIER_OPTIONS}
                    value={m.tier_cnp}
                    onChange={() => {}}
                    disabled={isOwner}
                    className="w-32"
                  />
                  <button
                    disabled={isOwner}
                    className="text-muted-foreground hover:text-danger transition-colors disabled:opacity-30 disabled:pointer-events-none"
                  >
                    <IconTrash size={15} />
                  </button>
                </li>
              );
            })}
        </ul>

        {/* Pending invitations */}
        {members.some((m) => m.status === 'pending_invite') && (
          <div className="mt-4">
            <p className="text-xs text-muted-foreground uppercase tracking-wide mb-2">
              Invitations en attente
            </p>
            <ul className="divide-y divide-border">
              {members
                .filter((m) => m.status === 'pending_invite')
                .map((m, i) => (
                  <li key={i} className="flex items-center gap-3 py-2.5">
                    <div className="h-7 w-7 flex items-center justify-center rounded-full bg-muted text-muted-foreground">
                      <IconClock size={14} />
                    </div>
                    <span className="flex-1 text-sm text-muted-foreground">{m.email}</span>
                    <Badge variant="muted">pending</Badge>
                    <button className="text-muted-foreground hover:text-danger transition-colors">
                      ×
                    </button>
                  </li>
                ))}
            </ul>
          </div>
        )}
      </Card>
      </div>
    </div>
  );
}
