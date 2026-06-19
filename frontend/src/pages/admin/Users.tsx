import { useQuery, useQueries, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { membersApi } from '@/api/members';
import { User, UserRole } from '@/types';

const patchUser = async (id: number, payload: { role?: UserRole; is_active?: boolean }) => {
  const { data } = await api.patch<User>(`/users/${id}`, payload);
  return data;
};

export const Users = () => {
  const queryClient = useQueryClient();

  const { data: users = [], isLoading } = useQuery({
    queryKey: ['admin-users'],
    queryFn: async () => {
      const { data } = await api.get<User[]>('/users/');
      return data;
    },
  });

  const groupQueries = useQueries({
    queries: users.map(u => ({
      queryKey: ['user-groups', u.id],
      queryFn: () => membersApi.getUserGroups(u.id),
      staleTime: 5 * 60 * 1000,
    })),
  });

  const mutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: { role?: UserRole; is_active?: boolean } }) =>
      patchUser(id, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-users'] }),
  });

  return (
    <>
      <div className="topbar">
        <span className="topbar-title">Gestion des utilisateurs</span>
      </div>
      <div className="page-content">
        {isLoading ? (
          <div className="loading-state">
            <i className="ti ti-loader-2" aria-hidden="true" style={{ fontSize: 16 }} />
            Chargement…
          </div>
        ) : (
          <div className="card">
            <div className="card-header">Utilisateurs ({users.length})</div>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Rôle</th>
                  <th>Statut</th>
                  <th>Groupes</th>
                  <th>Créé le</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user, idx) => {
                  const groups = groupQueries[idx]?.data ?? [];
                  return (
                    <tr key={user.id}>
                      <td style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{user.email}</td>
                      <td>
                        <select
                          className="role-select"
                          value={user.role}
                          onChange={e => mutation.mutate({ id: user.id, payload: { role: e.target.value as UserRole } })}
                        >
                          <option value="admin">admin</option>
                          <option value="dev">dev</option>
                          <option value="viewer">viewer</option>
                        </select>
                      </td>
                      <td>
                        <button
                          className={`badge ${user.is_active ? 'active' : 'inactive'}`}
                          style={{ cursor: 'pointer', border: 'none', background: undefined }}
                          onClick={() => mutation.mutate({ id: user.id, payload: { is_active: !user.is_active } })}
                          title={user.is_active ? 'Désactiver' : 'Activer'}
                        >
                          {user.is_active ? 'Actif' : 'Inactif'}
                        </button>
                      </td>
                      <td>
                        {groupQueries[idx]?.isLoading ? (
                          <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>…</span>
                        ) : groups.length === 0 ? (
                          <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>—</span>
                        ) : (
                          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                            {groups.map(g => (
                              <span key={g.gitlab_group_id} className="team-chip" title={g.full_path}>
                                {g.name}
                              </span>
                            ))}
                          </div>
                        )}
                      </td>
                      <td className="mono">{new Date(user.created_at).toLocaleDateString('fr-FR')}</td>
                    </tr>
                  );
                })}
                {users.length === 0 && (
                  <tr>
                    <td colSpan={5} style={{ textAlign: 'center', padding: '32px 16px', color: 'var(--text-muted)' }}>
                      Aucun utilisateur.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
};
