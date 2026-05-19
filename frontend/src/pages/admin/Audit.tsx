import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import { AuditLog } from '@/types';

export const Audit = () => {
  const { data: logs = [], isLoading } = useQuery({
    queryKey: ['admin-audit'],
    queryFn: async () => {
      const { data } = await api.get<AuditLog[]>('/audit/');
      return data;
    },
  });

  return (
    <>
      <div className="topbar">
        <span className="topbar-title">Logs d'audit</span>
      </div>
      <div className="page-content">
        {isLoading ? (
          <div className="loading-state">
            <i className="ti ti-loader-2" aria-hidden="true" style={{ fontSize: 16 }} />
            Chargement…
          </div>
        ) : (
          <div className="card">
            <div className="card-header">Événements ({logs.length})</div>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Horodatage</th>
                  <th>Utilisateur</th>
                  <th>Action</th>
                  <th>Cible</th>
                  <th>IP</th>
                </tr>
              </thead>
              <tbody>
                {logs.map(log => (
                  <tr key={log.id}>
                    <td className="mono">{new Date(log.timestamp).toLocaleString('fr-FR')}</td>
                    <td style={{ color: 'var(--text-primary)' }}>{log.user_id ?? 'System'}</td>
                    <td><span className="accent mono">{log.action}</span></td>
                    <td className="mono">
                      {log.cloud && <span className={`env-tag ${log.cloud}`} style={{ marginRight: 6 }}>{log.cloud.toUpperCase()}</span>}
                      {log.resource_id ? `#${log.resource_id}` : '—'}
                    </td>
                    <td className="mono">{log.ip_address ?? '—'}</td>
                  </tr>
                ))}
                {logs.length === 0 && (
                  <tr>
                    <td colSpan={5} style={{ textAlign: 'center', padding: '32px 16px', color: 'var(--text-muted)' }}>
                      Aucun événement d'audit.
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
