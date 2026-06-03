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


export const Resources = () => {
  const [filterStatus, setFilterStatus] = useState<DisplayStatus | ''>('');
  const [deleteModal, setDeleteModal] = useState<number | null>(null);
  const [syncError, setSyncError] = useState('');
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
          <button className="btn btn-primary" onClick={() => navigate('/resources/new')}>
            <i className="ti ti-plus" aria-hidden="true" />
            Nouvelle application
          </button>
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
