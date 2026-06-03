import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useLocation } from 'react-router-dom';
import { appsApi } from '@/api/apps';
import { ConfirmModal } from '@/components/ConfirmModal';
import { Application, ResourceStatus } from '@/types';
import { useAuthStore } from '@/store/auth';
import { APP_STATUS_MAP } from '@/utils/appStatus';
import { timeAgo } from '@/utils/timeAgo';

type DisplayStatus = ResourceStatus;

/* Mock apps shown when the API returns no data (demo / first run) */
interface MockApp {
  id: number;
  name: string;
  desc: string;
  env: string;
  source: 'imported' | 'scaffolded';
  status: DisplayStatus;
  repoPath: string;
  commitHash: string;
  pods: number;
  maxPods: number;
  created_at: string;
}

const MOCK_APPS: MockApp[] = [
  { id: -1, name: 'api-gateway', desc: 'Reverse proxy & authentication layer', env: 'production', source: 'scaffolded', status: 'running', repoPath: 'gitlab.com/…/api-gateway', commitHash: 'a3f8c12', pods: 3, maxPods: 3, created_at: new Date(Date.now() - 3 * 60 * 1000).toISOString() },
  { id: -2, name: 'user-service', desc: 'User management & profiles', env: 'production', source: 'scaffolded', status: 'pending', repoPath: 'gitlab.com/…/user-service', commitHash: 'e9d5c76', pods: 1, maxPods: 2, created_at: new Date(Date.now() - 30 * 1000).toISOString() },
  { id: -3, name: 'payment-worker', desc: 'Async payment processing', env: 'production', source: 'imported', status: 'error', repoPath: 'gitlab.com/…/payment-worker', commitHash: 'h6a2z43', pods: 0, maxPods: 2, created_at: new Date(Date.now() - 12 * 60 * 1000).toISOString() },
  { id: -4, name: 'frontend-app', desc: 'Main customer-facing interface', env: 'production', source: 'scaffolded', status: 'running', repoPath: 'gitlab.com/…/frontend-app', commitHash: 'j4y0x21', pods: 2, maxPods: 2, created_at: new Date(Date.now() - 60 * 60 * 1000).toISOString() },
  { id: -5, name: 'notif-service', desc: 'Email & push notifications', env: 'staging', source: 'imported', status: 'stopped', repoPath: 'gitlab.com/…/notif-service', commitHash: 'l2w8v09', pods: 0, maxPods: 0, created_at: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString() },
];

const SCAFFOLDED_ORIGINS = new Set(['gitlab', 'github', 'template', 'scaffold']);

function appToDisplay(app: Application): MockApp {
  const pods = app.status === 'deployed' ? 2 : app.status === 'onboarding' ? 1 : 0;
  const repoPath = app.repo_url
    ? app.repo_url.replace(/^https?:\/\//, '').replace(/\.git$/, '')
    : `gitlab.com/…/${app.name}`;
  const source: 'imported' | 'scaffolded' =
    app.origin && SCAFFOLDED_ORIGINS.has(app.origin) ? 'scaffolded' : 'imported';
  return {
    id: app.id,
    name: app.name,
    desc: app.owner,
    env: app.origin ?? 'k8s',
    source,
    status: APP_STATUS_MAP[app.status],
    repoPath,
    commitHash: '',
    pods,
    maxPods: pods > 0 ? Math.max(pods, 2) : 2,
    created_at: app.created_at,
  };
}

function statusLabel(s: DisplayStatus): string {
  return { running: 'Running', pending: 'Déploiement…', stopped: 'Arrêtée', terminated: 'Terminée', error: 'Échec' }[s];
}

function cardClass(s: DisplayStatus): string {
  if (s === 'error') return 'app-card is-error';
  if (s === 'stopped' || s === 'terminated') return 'app-card is-stopped';
  return 'app-card';
}

function PodBar({ status, pods, maxPods }: { status: DisplayStatus; pods: number; maxPods: number }) {
  return (
    <div className="pods-bar">
      {Array.from({ length: Math.max(maxPods, 1) }, (_, i) => (
        <div
          key={i}
          className={`pod-sq ${
            status === 'error' ? 'err' : i < pods ? 'on' : status === 'pending' ? 'amber' : 'off'
          }`}
        />
      ))}
    </div>
  );
}

const EMPTY_IMPORT_FORM = { name: '', owner: '', repo_url: '', framework: '' };

export const Resources = () => {
  const [filterStatus, setFilterStatus] = useState<DisplayStatus | ''>('');
  const [deleteModal, setDeleteModal] = useState<number | null>(null);
  const [syncError, setSyncError] = useState('');
  const [showDropdown, setShowDropdown] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [importForm, setImportForm] = useState(EMPTY_IMPORT_FORM);
  const [importError, setImportError] = useState<string | null>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const user = useAuthStore(s => s.user);

  const { data: apiApps = [], isLoading, refetch } = useQuery({
    queryKey: ['apps'],
    queryFn: () => appsApi.list(),
  });

  useEffect(() => {
    refetch();
  }, [location.key, refetch]);

  const apiDisplayApps = apiApps.map(appToDisplay);
  const filtered = filterStatus ? apiDisplayApps.filter(a => a.status === filterStatus) : apiDisplayApps;

  /* Fall back to mock data when API returns nothing */
  const displayApps = filtered.length > 0 || filterStatus ? filtered : (apiApps.length === 0 && !isLoading ? MOCK_APPS : []);
  const isMock = apiApps.length === 0 && !isLoading;

  const deleteMutation = useMutation({
    mutationFn: (id: number) => appsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['apps'] });
      setDeleteModal(null);
    },
  });

  const syncMutation = useMutation({
    mutationFn: () => appsApi.syncFromK8s(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['apps'] });
      setSyncError('');
    },
    onError: (err: any) => {
      const detail = err.response?.data?.detail;
      setSyncError(typeof detail === 'string' ? detail : 'Synchronisation échouée');
    },
  });

  const importMutation = useMutation({
    mutationFn: appsApi.importApp,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['apps'] });
      setShowImportModal(false);
      setImportForm(EMPTY_IMPORT_FORM);
      setImportError(null);
    },
    onError: (err: any) => {
      setImportError(err?.response?.data?.detail ?? "Erreur lors de l'import");
    },
  });

  const closeImportModal = () => {
    setShowImportModal(false);
    setImportForm(EMPTY_IMPORT_FORM);
    setImportError(null);
  };

  const handleImport = (e: React.FormEvent) => {
    e.preventDefault();
    setImportError(null);
    importMutation.mutate({
      name: importForm.name,
      owner: importForm.owner,
      repo_url: importForm.repo_url,
      framework: importForm.framework || undefined,
    });
  };

  return (
    <>
      <div className="topbar">
        <div className="topbar-left">
          <span className="topbar-title">Applications</span>
          <div className="heartbeat-pill">
            <span className="pill-count">{isMock ? MOCK_APPS.length : apiApps.length} apps</span>
            <div className="pill-beat">
              <svg width="52" height="18" viewBox="0 0 52 18" fill="none">
                <polyline
                  points="0,9 10,9 14,3 18,15 22,2 26,14 29,9 52,9"
                  stroke="#10B981"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  fill="none"
                />
              </svg>
            </div>
          </div>
          <div className="filters">
            <select
              className="filter-select"
              value={filterStatus}
              onChange={e => setFilterStatus(e.target.value as DisplayStatus)}
              style={{ border: 'none', outline: 'none' }}
            >
              <option value="">Statut : Tous</option>
              <option value="running">Running</option>
              <option value="pending">En déploiement</option>
              <option value="stopped">Arrêtée</option>
              <option value="error">Échec</option>
            </select>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {user?.role === 'admin' && (
            <button
              className="btn btn-ghost"
              onClick={() => syncMutation.mutate()}
              disabled={syncMutation.isPending}
              title="Importer les Deployments existants depuis Kubernetes"
            >
              <i className={`ti ${syncMutation.isPending ? 'ti-loader-2' : 'ti-refresh'}`} aria-hidden="true"
                style={syncMutation.isPending ? { animation: 'spin 1s linear infinite' } : undefined}
              />
              {syncMutation.isPending ? 'Sync…' : 'Sync K8s'}
            </button>
          )}
          <div
            style={{ position: 'relative' }}
            onMouseEnter={() => setShowDropdown(true)}
            onMouseLeave={() => setShowDropdown(false)}
          >
            <button className="btn btn-primary">
              <i className="ti ti-plus" aria-hidden="true" />
              Nouvelle application
              <i className="ti ti-chevron-down" aria-hidden="true" style={{ fontSize: 11, marginLeft: 2 }} />
            </button>
            {showDropdown && (
              <div className="dropdown-menu">
                <button
                  className="dropdown-item"
                  onClick={() => setShowDropdown(false)}
                  disabled
                  style={{ opacity: 0.45, cursor: 'default' }}
                >
                  <i className="ti ti-template" aria-hidden="true" />
                  Scaffolder une app
                  <span className="coming-badge" style={{ marginLeft: 'auto' }}>bientôt</span>
                </button>
                <button
                  className="dropdown-item"
                  onClick={() => { setShowDropdown(false); setImportForm(f => ({ ...f, owner: user?.email ?? '' })); setShowImportModal(true); }}
                >
                  <i className="ti ti-git-merge" aria-hidden="true" />
                  Importer un repo
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="page-content">
        {isLoading ? (
          <div className="loading-state">
            <i className="ti ti-loader-2" aria-hidden="true" style={{ fontSize: 16 }} />
            Chargement…
          </div>
        ) : (
          <>
            {syncError && (
              <div className="alert error">
                <i className="ti ti-alert-circle" aria-hidden="true" />
                {syncError}
              </div>
            )}
            {isMock && (
              <div className="alert info">
                <i className="ti ti-info-circle" aria-hidden="true" />
                Aucune application déployée — affichage des données de démonstration.
                {user?.role === 'admin' && ' Cliquez sur "Sync K8s" pour importer vos Deployments existants.'}
              </div>
            )}
            <div className="apps-grid">
              {displayApps.map(app => (
                <AppCard
                  key={app.id}
                  app={app}
                  onDelete={isMock ? () => {} : setDeleteModal}
                  onOpen={() => app.id > 0 ? navigate(`/resources/${app.id}`) : undefined}
                  isMock={isMock}
                />
              ))}
            </div>
          </>
        )}
      </div>

      <ConfirmModal
        isOpen={deleteModal !== null}
        title="Supprimer l'application"
        message="Cette action supprimera définitivement l'application et toutes ses données de déploiement. Cette opération est irréversible."
        onConfirm={() => deleteModal !== null && deleteMutation.mutate(deleteModal)}
        onCancel={() => setDeleteModal(null)}
        isLoading={deleteMutation.isPending}
      />

      {showImportModal && (
        <div className="modal-overlay" onClick={closeImportModal}>
          <div className="modal-box" style={{ width: 460 }} onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
              <div style={{ width: 32, height: 32, borderRadius: 8, background: 'rgba(26,107,240,0.08)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <i className="ti ti-git-merge" style={{ color: 'var(--accent)', fontSize: 16 }} aria-hidden="true" />
              </div>
              <div>
                <div className="modal-title" style={{ marginBottom: 0 }}>Importer une application</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 1 }}>Connectez un repo GitLab existant à la plateforme CNP</div>
              </div>
            </div>

            <div style={{ height: 1, background: 'var(--border)', margin: '16px 0' }} />

            <form onSubmit={handleImport} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <div className="form-group">
                  <label className="form-label">Nom de l'application <span style={{ color: 'var(--red)' }}>*</span></label>
                  <input
                    className="form-input"
                    placeholder="mon-service"
                    value={importForm.name}
                    onChange={e => setImportForm(f => ({ ...f, name: e.target.value }))}
                    required
                    autoFocus
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Responsable</label>
                  <input
                    className="form-input"
                    value={importForm.owner}
                    readOnly
                    style={{ color: 'var(--text-muted)', cursor: 'default' }}
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">URL du repo GitLab <span style={{ color: 'var(--red)' }}>*</span></label>
                <input
                  className="form-input mono"
                  placeholder="https://gitlab.example.com/cnp-apps/mon-service"
                  value={importForm.repo_url}
                  onChange={e => setImportForm(f => ({ ...f, repo_url: e.target.value }))}
                  required
                />
                <span className="form-hint">Doit être accessible par le bot CNP</span>
              </div>

              <div className="form-group">
                <label className="form-label">Framework</label>
                <select
                  className="form-select"
                  value={importForm.framework}
                  onChange={e => setImportForm(f => ({ ...f, framework: e.target.value }))}
                >
                  <option value="">Auto-détection</option>
                  <option value="python">Python</option>
                  <option value="generic">Generic</option>
                </select>
                <span className="form-hint">Laissez vide pour la détection automatique</span>
              </div>

              {importError && (
                <div className="alert error">
                  <i className="ti ti-alert-circle" aria-hidden="true" />
                  {importError}
                </div>
              )}

              <div className="modal-actions" style={{ marginTop: 4 }}>
                <button type="button" className="btn btn-ghost" onClick={closeImportModal} disabled={importMutation.isPending}>
                  Annuler
                </button>
                <button type="submit" className="btn btn-primary" disabled={importMutation.isPending}>
                  {importMutation.isPending ? (
                    <>
                      <i className="ti ti-loader-2" aria-hidden="true" style={{ animation: 'spin 1s linear infinite' }} />
                      Import en cours…
                    </>
                  ) : (
                    <>
                      <i className="ti ti-git-merge" aria-hidden="true" />
                      Importer
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
};

function SourceBadge({ source }: { source: 'imported' | 'scaffolded' }) {
  const isImported = source === 'imported';
  return (
    <span style={{
      fontSize: 9, fontWeight: 600, letterSpacing: '0.06em',
      textTransform: 'uppercase',
      color: isImported ? 'var(--text-muted)' : 'var(--accent)',
      border: `1px solid ${isImported ? 'var(--border)' : 'color-mix(in srgb, var(--accent) 40%, transparent)'}`,
      borderRadius: 4,
      padding: '1px 5px', lineHeight: '16px',
      whiteSpace: 'nowrap',
    }}>
      {isImported ? 'imported' : 'scaffolded'}
    </span>
  );
}

function AppCard({ app, onOpen, onDelete, isMock }: {
  app: MockApp;
  onOpen: () => void;
  onDelete: (id: number) => void;
  isMock?: boolean;
}) {
  const { id, name, desc, env, source, status, repoPath, commitHash, pods, maxPods, created_at } = app;

  return (
    <div className={cardClass(status)} onClick={onOpen} style={{ cursor: isMock ? 'default' : 'pointer' }}>
      <div className="card-top">
        <div>
          <div className="app-name">{name}</div>
          <div className="app-desc">{desc}</div>
          <span className={`env-tag ${env}`} style={{ marginTop: 6, display: 'inline-block' }}>{env}</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <SourceBadge source={source} />
            <div className="status-line">
              <span className={`status-dot ${status}`} />
              <span className={`status-text ${status}`}>{statusLabel(status)}</span>
            </div>
          </div>
          {!isMock && (
            <button
              className="btn-icon"
              style={{ width: 24, height: 24 }}
              onClick={e => { e.stopPropagation(); onDelete(id); }}
              title="Supprimer"
            >
              <i className="ti ti-trash" aria-hidden="true" style={{ fontSize: 13 }} />
            </button>
          )}
        </div>
      </div>

      <div className="card-meta">
        <span className="app-repo">{repoPath}</span>
        {commitHash && <span className="commit-hash">{commitHash.slice(0, 7)}</span>}
      </div>

      <div className="card-footer">
        <div className="pods-info">
          <PodBar status={status} pods={pods} maxPods={maxPods} />
          <span className={`pods-count${status === 'error' ? ' error' : ''}`}>
            {pods} / {maxPods} pods
          </span>
        </div>
        <span className="time-ago">{timeAgo(created_at)}</span>
      </div>
    </div>
  );
}
