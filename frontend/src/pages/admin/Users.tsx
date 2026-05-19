import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import { User } from '@/types';

export const Users = () => {
  const { data: users = [], isLoading } = useQuery({
    queryKey: ['admin-users'],
    queryFn: async () => {
      const { data } = await api.get<User[]>('/users/');
      return data;
    },
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
                  <th>Créé le</th>
                </tr>
              </thead>
              <tbody>
                {users.map(user => (
                  <tr key={user.id}>
                    <td style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{user.email}</td>
                    <td>
                      <span className={`badge ${user.role}`}>{user.role}</span>
                    </td>
                    <td>
                      <span className={`badge ${user.is_active ? 'active' : 'inactive'}`}>
                        {user.is_active ? 'Actif' : 'Inactif'}
                      </span>
                    </td>
                    <td className="mono">{new Date(user.created_at).toLocaleDateString('fr-FR')}</td>
                  </tr>
                ))}
                {users.length === 0 && (
                  <tr>
                    <td colSpan={4} style={{ textAlign: 'center', padding: '32px 16px', color: 'var(--text-muted)' }}>
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
