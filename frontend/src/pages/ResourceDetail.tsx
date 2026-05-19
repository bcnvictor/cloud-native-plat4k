import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { appsApi } from '@/api/apps';
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

const MOCK_LOGS = [
  ['10:23:01', 'INFO', 'Application initialized successfully'],
  ['10:23:45', 'INFO', 'Health check passed'],
  ['10:26:33', 'WARN', 'High resource usage: 95%'],
  ['10:28:00', 'INFO', 'Auto-scaling triggered'],
  ['10:30:02', 'INFO', 'Health check passed — all services healthy'],
  ['10:31:18', 'INFO', 'Metrics reported to monitoring'],
];

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
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-ghost">
              <i className="ti ti-terminal-2" aria-hidden="true" />Logs
            </button>
            <button className="btn btn-primary">
              <i className="ti ti-rocket" aria-hidden="true" />Déployer
            </button>
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

              <div className="meta-card" style={{ position: 'relative' }}>
                <div className="meta-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  Ressources — usage
                  <SoonBadge />
                </div>
                <div style={{ opacity: 0.4, pointerEvents: 'none' }}>
                  <div className="resource-bar-header">
                    <span>CPU</span><span>—</span>
                  </div>
                  <div className="resource-bar-track">
                    <div className="resource-bar-fill" style={{ width: '0%', background: 'var(--accent)' }} />
                  </div>
                  <div className="resource-bar-header">
                    <span>Mémoire</span><span>—</span>
                  </div>
                  <div className="resource-bar-track">
                    <div className="resource-bar-fill" style={{ width: '0%', background: 'var(--green)' }} />
                  </div>
                </div>
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
          <div style={{ position: 'relative' }}>
            <div className="terminal" style={{ filter: 'blur(2px)', opacity: 0.35, pointerEvents: 'none', userSelect: 'none' }}>
              <div className="terminal-header">
                <div className="terminal-dots">
                  {['#EF4444', '#F59E0B', '#10B981'].map(c => (
                    <div key={c} className="terminal-dot" style={{ background: c }} />
                  ))}
                </div>
                <span className="terminal-title">{name} — stdout</span>
                <div className="logs-live"><span className="live-dot" />live</div>
              </div>
              <div className="terminal-body">
                {MOCK_LOGS.map(([ts, lvl, msg], i) => (
                  <div key={i}>
                    <span style={{ color: 'rgba(255,255,255,0.25)', marginRight: 10 }}>{ts}</span>
                    <span style={{ color: lvl === 'INFO' ? '#6EE7B7' : lvl === 'WARN' ? '#FCD34D' : '#FCA5A5', marginRight: 8 }}>{lvl}</span>
                    <span style={{ color: 'rgba(255,255,255,0.65)' }}>{msg}</span>
                  </div>
                ))}
              </div>
            </div>
            <div style={{
              position: 'absolute', inset: 0,
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              gap: 10,
            }}>
              <i className="ti ti-clock" aria-hidden="true" style={{ fontSize: 28, color: 'var(--text-muted)' }} />
              <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-secondary)' }}>Logs en temps réel — bientôt disponible</span>
              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Intégration kubectl logs / Loki à venir</span>
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
                  Supprimer détruit définitivement l'application et toutes ses données de déploiement. Cette action est irréversible.
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
        message="Supprimer détruit définitivement l'application et toutes ses données de déploiement. Cette action est irréversible."
        onConfirm={() => deleteMutation.mutate()}
        onCancel={() => setShowDeleteModal(false)}
        isLoading={deleteMutation.isPending}
      />
    </>
  );
};
