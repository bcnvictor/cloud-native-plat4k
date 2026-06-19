import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { usersApi } from '@/api/users';
import { membersApi } from '@/api/members';
import { CnpTier } from '@/types';

const TIER_COLOR: Record<CnpTier, string> = {
  viewer: '#888',
  developer: '#4a9eff',
  maintainer: '#4caf50',
  owner: '#f0b429',
};

export const Profile = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: me, isLoading } = useQuery({
    queryKey: ['me'],
    queryFn: () => usersApi.getMe(),
  });

  const { data: groups = [], isLoading: groupsLoading } = useQuery({
    queryKey: ['my-groups'],
    queryFn: () => membersApi.getMyGroups(),
  });

  const syncMutation = useMutation({
    mutationFn: () => membersApi.syncTeams(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-groups'] });
      queryClient.invalidateQueries({ queryKey: ['apps'] });
    },
  });

  return (
    <>
      <div className="topbar">
        <div className="topbar-left">
          <button className="btn-icon" onClick={() => navigate(-1)}>
            <i className="ti ti-arrow-left" aria-hidden="true" />
          </button>
          <span className="topbar-title">Mon profil</span>
        </div>
        <button
          className="btn btn-ghost"
          onClick={() => syncMutation.mutate()}
          disabled={syncMutation.isPending}
          title="Synchroniser mes équipes depuis GitLab"
        >
          <i className={`ti ${syncMutation.isPending ? 'ti-loader-2' : 'ti-refresh'}`} aria-hidden="true"
            style={syncMutation.isPending ? { animation: 'spin 1s linear infinite' } : undefined}
          />
          {syncMutation.isPending ? 'Sync…' : 'Sync mes équipes'}
        </button>
      </div>

      <div className="page-content">
        {isLoading ? (
          <div className="loading-state">
            <i className="ti ti-loader-2" aria-hidden="true" style={{ fontSize: 16 }} />
            Chargement…
          </div>
        ) : me && (
          <>
            <div className="card" style={{ marginBottom: 16 }}>
              <div className="card-header">Identité</div>
              <table className="env-table">
                <tbody>
                  <tr className="env-row">
                    <td className="env-key">Email</td>
                    <td className="env-val-cell" style={{ fontWeight: 500 }}>{me.email}</td>
                  </tr>
                  <tr className="env-row">
                    <td className="env-key">Rôle CNP</td>
                    <td className="env-val-cell">
                      <span className={`badge ${me.role}`}>{me.role}</span>
                    </td>
                  </tr>
                  {me.is_admin && (
                    <tr className="env-row">
                      <td className="env-key">Droits</td>
                      <td className="env-val-cell">
                        <span className="badge admin">
                          <i className="ti ti-shield-check" style={{ fontSize: 10 }} /> Admin CNP
                        </span>
                      </td>
                    </tr>
                  )}
                  {me.gitlab_user_id && (
                    <tr className="env-row">
                      <td className="env-key">GitLab ID</td>
                      <td className="env-val-cell mono">{me.gitlab_user_id}</td>
                    </tr>
                  )}
                  <tr className="env-row">
                    <td className="env-key">Membre depuis</td>
                    <td className="env-val-cell">{new Date(me.created_at).toLocaleDateString('fr-FR')}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div className="card" style={{ marginBottom: 16 }}>
              <div className="card-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span>Mes groupes GitLab</span>
                <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{groups.length} groupe{groups.length !== 1 ? 's' : ''}</span>
              </div>
              {groupsLoading ? (
                <div style={{ padding: '16px', color: 'var(--text-muted)', fontSize: 12 }}>Chargement…</div>
              ) : groups.length === 0 ? (
                <div style={{ padding: '16px', color: 'var(--text-muted)', fontSize: 12 }}>
                  Aucun groupe synchronisé. Cliquez sur "Sync mes équipes" pour importer vos groupes GitLab.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                  {groups.map(g => (
                    <div key={g.gitlab_group_id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', borderBottom: '1px solid var(--border)' }}>
                      <div style={{
                        width: 32, height: 32, borderRadius: 6, flexShrink: 0,
                        background: 'color-mix(in srgb, var(--accent) 12%, transparent)',
                        border: '1px solid color-mix(in srgb, var(--accent) 25%, transparent)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                      }}>
                        <i className="ti ti-users-group" style={{ fontSize: 14, color: 'var(--accent)' }} />
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 13, fontWeight: 500 }}>{g.name}</div>
                        <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--mono)' }}>{g.full_path}</div>
                      </div>
                      <span style={{
                        fontSize: 10, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase',
                        color: TIER_COLOR[g.tier_cnp],
                        border: `1px solid ${TIER_COLOR[g.tier_cnp]}`,
                        borderRadius: 4, padding: '2px 7px',
                      }}>
                        {g.tier_cnp}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="card">
              <div className="card-header">Accès rapide</div>
              <div style={{ padding: '12px 16px', display: 'flex', gap: 8 }}>
                <button className="btn btn-ghost" onClick={() => navigate('/apikeys')}>
                  <i className="ti ti-key" aria-hidden="true" /> Mes clés API
                </button>
                <button className="btn btn-ghost" onClick={() => navigate('/credentials')}>
                  <i className="ti ti-settings" aria-hidden="true" /> Paramètres
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
};
