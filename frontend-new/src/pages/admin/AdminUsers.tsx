import { useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useScopeStore } from '@/store/scope';
import { Breadcrumb } from '@/components/Breadcrumb';
import { usersApi } from '@/api/users';
import { Skeleton } from '@/components/ui/skeleton';
import { Select } from '@/components/ui/Select';
import { Badge } from '@/components/ui/Badge';
import { UserRole } from '@/types';
import { timeAgo } from '@/utils/timeAgo';

const ROLE_OPTIONS: { value: UserRole; label: string }[] = [
  { value: 'admin', label: 'Admin' },
  { value: 'dev', label: 'Dev' },
  { value: 'viewer', label: 'Viewer' },
];

export function AdminUsers() {
  const { setScope } = useScopeStore();
  useEffect(() => { setScope('admin'); }, [setScope]);

  const qc = useQueryClient();

  const { data: users = [], isLoading } = useQuery({
    queryKey: ['admin-users'],
    queryFn: usersApi.list,
  });

  const patchMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: { role?: UserRole; is_active?: boolean } }) =>
      usersApi.patch(id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-users'] }),
  });

  return (
    <div className="max-w-[1440px] mx-auto px-8 py-6">
      <div className="mb-6">
        <Breadcrumb items={[{ label: 'Plateforme', to: '/admin/clusters' }, { label: 'Utilisateurs' }]} />
        <h1 className="text-xl font-semibold text-foreground">Utilisateurs</h1>
        <p className="text-sm text-muted-foreground">
          {users.length} utilisateur{users.length !== 1 ? 's' : ''}
        </p>
      </div>

      <div className="bg-card border border-border rounded-md overflow-hidden">
        <div className="grid grid-cols-[2fr_1fr_1fr_1fr_auto] gap-4 px-4 py-2 border-b border-border bg-background-subtle">
          {['Email', 'Rôle', 'Statut', 'Membre depuis', ''].map((h) => (
            <p key={h} className="text-xs font-medium text-muted-foreground">{h}</p>
          ))}
        </div>

        {isLoading
          ? Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="px-4 py-3 border-b border-border last:border-0">
                <Skeleton className="h-6 w-full rounded" />
              </div>
            ))
          : users.map((u) => (
              <div
                key={u.id}
                className="grid grid-cols-[2fr_1fr_1fr_1fr_auto] gap-4 px-4 py-2.5 border-b border-border last:border-0 items-center"
              >
                <div className="min-w-0">
                  <p className="text-sm text-foreground truncate">{u.email}</p>
                  {u.is_admin && (
                    <span className="text-xs text-muted-foreground">superadmin</span>
                  )}
                </div>

                <Select
                  options={ROLE_OPTIONS}
                  value={u.role}
                  onChange={(v) => patchMutation.mutate({ id: u.id, payload: { role: v as UserRole } })}
                  className="w-28"
                  disabled={u.is_admin}
                />

                <button
                  onClick={() => patchMutation.mutate({ id: u.id, payload: { is_active: !u.is_active } })}
                  disabled={u.is_admin}
                  className="justify-self-start"
                >
                  <Badge variant={u.is_active ? 'success' : 'muted'}>
                    {u.is_active ? 'actif' : 'inactif'}
                  </Badge>
                </button>

                <p className="text-xs text-muted-foreground">{timeAgo(u.created_at)}</p>

                <span />
              </div>
            ))}

        {!isLoading && users.length === 0 && (
          <p className="px-4 py-8 text-sm text-muted-foreground text-center">
            Aucun utilisateur.
          </p>
        )}
      </div>
    </div>
  );
}
