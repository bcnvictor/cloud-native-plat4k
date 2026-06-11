import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { appsApi } from '@/api/apps';
import { monitoringApi } from '@/api/monitoring';
import { grafanaLogsUrl, grafanaMetricsUrl } from '@/utils/grafanaLinks';
import { ResourceStatus } from '@/types';
import { ConfirmModal } from '@/components/ConfirmModal';
import { APP_STATUS_MAP } from '@/utils/appStatus';
import { timeAgo } from '@/utils/timeAgo';

const SoonBadge = () => (
  <span style={{
    fontSize: 9, fontWeight: 600, letterSpacing: '0.05em',
    textTransform: 'uppercase', color: 'var(--accent)',
    border: '1px solid var(--accent)', borderRadius: 4,
    padding: '1px 5px', lineHeight: '14px', opacity: 0.8,
  }}>
    Bientôt
  </span>
);

type DisplayStatus = ResourceStatus;

const STATUS_LABEL: Record<DisplayStatus, string> = {
  running: 'Running',
  pending: 'Déploiement…',
  stopped: 'Arrêtée',
  terminated: 'Terminée',
  error: 'Échec',
};

const levelColor = (level: string) => {
  switch (level) {
    case 'ERROR': case 'CRITICAL': case 'FATAL': return '#FCA5A5';
    case 'WARN': return '#FCD34D';
    case 'DEBUG': return 'rgba(255,255,255,0.35)';
    default: return '#6EE7B7';
  }
};

export const ResourceDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<'overview' | 'logs' | 'config'>('overview');
  const [showDeleteModal, setShowDeleteModal] = useState(false);

  const { data: app, isLoading, isError } = useQuery({
    queryKey: ['app', id],
    queryFn: () => appsApi.get(Number(id)),
    enabled: !!id,
  });

  const { data: deployments = [] } = useQuery({
    queryKey: ['deployments', id],
    queryFn: () => appsApi.listDeployments(Number(id)),
    enabled: !!id,
  });

  const { data: monitoringConfig } = useQuery({
    queryKey: ['monitoring-config'],
    queryFn: monitoringApi.getConfig,
    staleTime: Infinity,
  });

  const { data: metrics } = useQuery({
    queryKey: ['monitoring-metrics'],
    queryFn: monitoringApi.getMetrics,
    refetchInterval: 30_000,
    staleTime: 20_000,
    enabled: !!app,
  });

  const { data: appLogs = [], isLoading: logsLoading, isError: logsError } = useQuery({
    queryKey: ['app-logs', app?.name],
    queryFn: () => monitoringApi.getAppLogs(app!.name, 50),
    enabled: tab === 'logs' && !!app,
    refetchInterval: 30_000,
  });

  const deleteMutation = useMutation({
    mutationFn: () => appsApi.delete(Number(id)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['apps'] });
      navigate('/resources');
    },
  });

  if (isLoading) {
    return (
      <>
        <div className="topbar"><span className="topbar-title">Application</span></div>
        <div className="loading-state">
          <i className="ti ti-loader-2" aria-hidden="true" style={{ fontSize: 16 }} />
          Chargement…
        </div>
      </>
    );
  }

  if (isError || !app) {
    return (
      <>
        <div className="topbar"><span className="topbar-title">Application</span></div>
        <div className="page-content">
          <div className="alert error">
            <i className="ti ti-alert-circle" aria-hidden="true" />
            Impossible de charger l'application.
          </div>
        </div>
      </>
    );
  }

  const { name, owner, origin, repo_url, status, created_at } = app;
  const displayStatus = APP_STATUS_MAP[status];

  const appCpu = metrics?.cpu_by_app.find(r => r.app === name);
  const appRam = metrics?.ram_by_app.find(r => r.app === name);
  const maxCpu = metrics?.cpu_by_app.reduce((m, r) => Math.max(m, r.value), 0.001) ?? 0.001;
  const maxRam = metrics?.ram_by_app.reduce((m, r) => Math.max(m, r.value), 1) ?? 1;

  const deleteMessage = origin === 'scaffolded'
    ? "Cette action supprimera définitivement l'application de la base de données, les manifestes de déploiement (GitOps/ArgoCD), ainsi que le dépôt source sur GitLab. Cette action est irréversible."
    : "Cette action supprimera définitivement l'application de la base de données et les manifestes de déploiement (GitOps/ArgoCD). Le dépôt source sur GitLab ne sera PAS supprimé. Cette action est irréversible.";

  return (
    <>
      <div className="app-header">
        <div className="app-header-top">
          <div className="app-header-left">
            <button className="btn-icon" onClick={() => navigate('/resources')}>
              <i className="ti ti-arrow-left" aria-hidden="true" />
            </button>
            <span className="app-header-name">{name}</span>
            <div className="status-line">
              <span className={`status-dot ${displayStatus}`} />
              <span className={`status-text ${displayStatus}`}>{STATUS_LABEL[displayStatus]}</span>
            </div>
            {origin && <span className={`env-tag ${origin}`}>{origin}</span>}
          </div>
        </div>
        <div className="tabs">
          {(['overview', 'logs', 'config'] as const).map(t => (
            <button key={t} className={`tab${tab === t ? ' active' : ''}`} onClick={() => setTab(t)}>
              {t === 'overview' ? 'Vue d\'ensemble' : t === 'logs' ? 'Logs' : 'Configuration'}
            </button>
          ))}
        </div>
      </div>

      <div className="page-content">
        {tab === 'overview' && (
          <>
            <div className="meta-row">
              <div className="meta-card">
                <div className="meta-label">Statut</div>
                <div className="meta-kv">
                  <span className="meta-kv-key">Statut</span>
                  <span className={`meta-kv-val ${displayStatus === 'running' ? 'green' : ''}`}>{STATUS_LABEL[displayStatus]}</span>
                </div>
                <div className="meta-kv">
                  <span className="meta-kv-key">Propriétaire</span>
                  <span className="meta-kv-val">{owner}</span>
                </div>
                <div className="meta-kv">
                  <span className="meta-kv-key">Environnement</span>
                  <span className="meta-kv-val">{origin ?? 'k8s'}</span>
                </div>
                <div className="meta-kv">
                  <span className="meta-kv-key">Créé</span>
                  <span className="meta-kv-val">{timeAgo(created_at)}</span>
                </div>
              </div>

              <div className="meta-card">
                <div className="meta-label" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span>Ressources — usage</span>
                  {monitoringConfig?.grafana_url && (
                    <a href={grafanaMetricsUrl(monitoringConfig.grafana_url, name)} target="_blank" rel="noopener noreferrer" style={{ fontSize: 10, color: 'var(--text-muted)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 3 }}>
                      <i className="ti ti-external-link" style={{ fontSize: 10 }} />Grafana
                    </a>
                  )}
                </div>
                {!metrics ? (
                  <div style={{ color: 'var(--text-muted)', fontSize: 11, padding: '8px 0' }}>Prometheus indisponible</div>
                ) : (
                  <>
                    <div className="resource-bar-header">
                      <span>CPU</span>
                      <span style={{ fontFamily: 'var(--mono)' }}>{appCpu ? (appCpu.value < 0.01 ? `${(appCpu.value * 1000).toFixed(1)}m` : `${appCpu.value.toFixed(3)} cores`) : '—'}</span>
                    </div>
                    <div className="resource-bar-track">
                      <div className="resource-bar-fill" style={{ width: `${appCpu ? (appCpu.value / maxCpu) * 100 : 0}%`, background: 'var(--accent)' }} />
                    </div>
                    <div className="resource-bar-header">
                      <span>Mémoire</span>
                      <span style={{ fontFamily: 'var(--mono)' }}>{appRam ? `${appRam.value.toFixed(0)} Mo` : '—'}</span>
                    </div>
                    <div className="resource-bar-track">
                      <div className="resource-bar-fill" style={{ width: `${appRam ? (appRam.value / maxRam) * 100 : 0}%`, background: 'var(--green)' }} />
                    </div>
                  </>
                )}
              </div>

              <div className="meta-card">
                <div className="meta-label">Dépôt</div>
                {repo_url && (
                  <div className="meta-kv">
                    <span className="meta-kv-key">URL</span>
                    <span className="meta-kv-val accent" style={{ fontSize: 10, maxWidth: 160, wordBreak: 'break-all' }}>{repo_url}</span>
                  </div>
                )}
                <div className="meta-kv">
                  <span className="meta-kv-key">Déploiements</span>
                  <span className="meta-kv-val">{deployments.length}</span>
                </div>
                <div className="meta-kv">
                  <span className="meta-kv-key">Dernier statut</span>
                  <span className="meta-kv-val">{deployments[0]?.status ?? '—'}</span>
                </div>
              </div>
            </div>

            <div className="card">
              <div className="card-header">Historique de déploiement</div>
              {deployments.length > 0 ? deployments.slice(0, 5).map((d) => (
                <div key={d.id} className="deploy-row">
                  <div className={`deploy-icon ${d.status === 'succeeded' || d.status === 'running' ? 'ok' : 'fail'}`}>
                    <i className={`ti ti-${d.status === 'succeeded' || d.status === 'running' ? 'check' : 'x'}`} aria-hidden="true" />
                  </div>
                  <span className="deploy-hash">v{d.version}</span>
                  <span className="deploy-msg">Déploiement #{d.id}</span>
                  <span className="deploy-author">cluster #{d.cluster_id}</span>
                  <span className="deploy-duration">{d.status}</span>
                  <span className="deploy-time">{timeAgo(d.created_at)}</span>
                </div>
              )) : (
                [
                  ['Déploiement initial', 'ok', 'system', '1m 24s', timeAgo(created_at)],
                  ['Mise à jour config', 'ok', 'system', '0m 45s', 'il y a 2h'],
                  ['Rollback version', 'fail', 'system', '0m 12s', 'il y a 1j'],
                ].map(([msg, st, author, dur, time], idx) => (
                  <div key={idx} className="deploy-row">
                    <div className={`deploy-icon ${st}`}>
                      <i className={`ti ti-${st === 'ok' ? 'check' : 'x'}`} aria-hidden="true" />
                    </div>
                    <span className="deploy-hash">—</span>
                    <span className="deploy-msg">{msg}</span>
                    <span className="deploy-author">{author}</span>
                    <span className="deploy-duration">{dur}</span>
                    <span className="deploy-time">{time}</span>
                  </div>
                ))
              )}
            </div>
          </>
        )}

        {tab === 'logs' && (
          <div className="terminal">
            <div className="terminal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div className="terminal-dots">
                  {['#EF4444', '#F59E0B', '#10B981'].map(c => (
                    <div key={c} className="terminal-dot" style={{ background: c }} />
                  ))}
                </div>
                <span className="terminal-title">{name} — stdout</span>
                {!logsError && !logsLoading && <div className="logs-live"><span className="live-dot" />live</div>}
              </div>
              {monitoringConfig?.grafana_url && (
                <a href={grafanaLogsUrl(monitoringConfig.grafana_url, name)} target="_blank" rel="noopener noreferrer" style={{ fontSize: 10, color: 'rgba(255,255,255,0.3)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 3 }}>
                  <i className="ti ti-external-link" style={{ fontSize: 10 }} />Grafana
                </a>
              )}
            </div>
            <div className="terminal-body">
              {logsLoading && (
                <div style={{ color: 'rgba(255,255,255,0.35)' }}>Chargement…</div>
              )}
              {logsError && (
                <div style={{ color: '#FCA5A5' }}>Loki indisponible — logs inaccessibles</div>
              )}
              {!logsLoading && !logsError && appLogs.length === 0 && (
                <div style={{ color: 'rgba(255,255,255,0.35)' }}>Aucun log trouvé pour cette application</div>
              )}
              {appLogs.map((entry, i) => (
                <div key={i}>
                  <span style={{ color: 'rgba(255,255,255,0.25)', marginRight: 10 }}>
                    {new Date(entry.ts * 1000).toISOString().slice(11, 19)}
                  </span>
                  <span style={{ color: levelColor(entry.level), marginRight: 8 }}>{entry.level}</span>
                  <span style={{ color: 'rgba(255,255,255,0.65)' }}>{entry.msg}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {tab === 'config' && (
          <>
            <div className="card">
              <div className="card-header">Informations</div>
              <table className="env-table">
                <tbody>
                  <tr className="env-row">
                    <td className="env-key">Nom</td>
                    <td className="env-val-cell">{name}</td>
                  </tr>
                  <tr className="env-row">
                    <td className="env-key">Propriétaire</td>
                    <td className="env-val-cell">{owner}</td>
                  </tr>
                  {origin && (
                    <tr className="env-row">
                      <td className="env-key">Origine</td>
                      <td className="env-val-cell">{origin}</td>
                    </tr>
                  )}
                  {repo_url && (
                    <tr className="env-row">
                      <td className="env-key">Dépôt</td>
                      <td className="env-val-cell">{repo_url}</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="card">
              <div className="card-header" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                Ressources allouées <SoonBadge />
              </div>
              <div style={{ padding: '14px 16px', opacity: 0.4, pointerEvents: 'none' }}>
                <div className="resource-bar-header">
                  <span style={{ color: 'var(--text-secondary)', fontSize: 11 }}>CPU request / limit</span>
                  <span style={{ fontFamily: 'var(--mono)', fontWeight: 500, fontSize: 11 }}>— / —</span>
                </div>
                <div className="resource-bar-track">
                  <div className="resource-bar-fill" style={{ width: '0%', background: '#93B8FA' }} />
                </div>
                <div className="resource-bar-header">
                  <span style={{ color: 'var(--text-secondary)', fontSize: 11 }}>Mémoire request / limit</span>
                  <span style={{ fontFamily: 'var(--mono)', fontWeight: 500, fontSize: 11 }}>— / —</span>
                </div>
                <div className="resource-bar-track">
                  <div className="resource-bar-fill" style={{ width: '0%', background: '#6EE7B7' }} />
                </div>
              </div>
            </div>

            <div className="danger-zone">
              <div className="danger-header">Danger zone</div>
              <div className="danger-body">
                <div className="danger-desc">
                  {deleteMessage}
                </div>
                <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
                  <button className="btn-danger" onClick={() => setShowDeleteModal(true)} disabled={deleteMutation.isPending}>
                    Supprimer
                  </button>
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      <ConfirmModal
        isOpen={showDeleteModal}
        title="Supprimer l'application"
        message={deleteMessage}
        onConfirm={() => deleteMutation.mutate()}
        onCancel={() => setShowDeleteModal(false)}
        isLoading={deleteMutation.isPending}
      />
    </>
  );
};
