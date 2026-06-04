import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { appsApi, AppTemplate } from '@/api/apps';
import { clustersApi } from '@/api/clusters';
import { useAuthStore } from '@/store/auth';

type Mode = 'scaffold' | 'onboard' | 'import';

const EMPTY_SCAFFOLD = { name: '', template: '', port: '8000', replicas: '1' };
const EMPTY_ONBOARD = { name: '', repo_url: '', framework: '', target_cluster_id: '' };
const EMPTY_IMPORT = { name: '', source_url: '', framework: '', target_cluster_id: '', raw: false };

export const NewApp = () => {
  const [mode, setMode] = useState<Mode>('scaffold');
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const user = useAuthStore(s => s.user);
  const owner = user?.email ?? '';

  const [scaffoldForm, setScaffoldForm] = useState(EMPTY_SCAFFOLD);
  const [scaffoldError, setScaffoldError] = useState<string | null>(null);

  const [onboardForm, setOnboardForm] = useState(EMPTY_ONBOARD);
  const [onboardError, setOnboardError] = useState<string | null>(null);

  const [importForm, setImportForm] = useState(EMPTY_IMPORT);
  const [importError, setImportError] = useState<string | null>(null);

  const { data: clusters = [] } = useQuery({
    queryKey: ['clusters'],
    queryFn: () => clustersApi.list(),
  });

  const { data: templates = [], isLoading: templatesLoading, isError: templatesErr } = useQuery({
    queryKey: ['app-templates'],
    queryFn: () => appsApi.listTemplates(),
    enabled: mode === 'scaffold',
    staleTime: 60_000,
  });

  const scaffoldMutation = useMutation({
    mutationFn: appsApi.scaffoldApp,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['apps'] });
      navigate('/resources');
    },
    onError: (err: unknown) => {
      setScaffoldError((err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Erreur lors du scaffolding');
    },
  });

  const onboardMutation = useMutation({
    mutationFn: appsApi.onboardApp,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['apps'] });
      navigate('/resources');
    },
    onError: (err: any) => {
      setOnboardError(err?.response?.data?.detail ?? "Erreur lors de l'onboarding");
    },
  });

  const importMutation = useMutation({
    mutationFn: appsApi.importApp,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['apps'] });
      navigate('/resources');
    },
    onError: (err: any) => {
      setImportError(err?.response?.data?.detail ?? "Erreur lors de l'import");
    },
  });

  const handleScaffold = (e: React.FormEvent) => {
    e.preventDefault();
    setScaffoldError(null);
    scaffoldMutation.mutate({
      name: scaffoldForm.name,
      owner,
      template: scaffoldForm.template,
      scaffolding: {
        port: Number(scaffoldForm.port) || 8000,
        replicas: Number(scaffoldForm.replicas) || 1,
      },
    });
  };

  const handleOnboard = (e: React.FormEvent) => {
    e.preventDefault();
    setOnboardError(null);
    onboardMutation.mutate({
      name: onboardForm.name,
      owner,
      repo_url: onboardForm.repo_url,
      framework: onboardForm.framework || undefined,
      target_cluster_id: onboardForm.target_cluster_id ? Number(onboardForm.target_cluster_id) : undefined,
    });
  };

  const handleImport = (e: React.FormEvent) => {
    e.preventDefault();
    setImportError(null);
    importMutation.mutate({
      name: importForm.name,
      owner,
      source_url: importForm.source_url,
      framework: importForm.framework || undefined,
      target_cluster_id: importForm.target_cluster_id ? Number(importForm.target_cluster_id) : undefined,
      raw: importForm.raw,
    });
  };

  return (
    <>
      <div className="topbar">
        <div className="topbar-left">
          <button
            className="btn btn-ghost"
            onClick={() => navigate('/resources')}
            style={{ gap: 5 }}
          >
            <i className="ti ti-arrow-left" aria-hidden="true" style={{ fontSize: 13 }} />
            Applications
          </button>
          <div style={{ width: 1, height: 16, background: 'var(--border-strong)' }} />
          <span className="topbar-title">Nouvelle application</span>
        </div>
      </div>

      <div className="page-content" style={{ alignItems: 'center' }}>
        <div style={{ width: '100%', maxWidth: 560, display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Mode selector */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
            <ModeCard
              icon="ti-template"
              label="Scaffolder une app"
              desc="Générer un projet depuis un template CNP"
              active={mode === 'scaffold'}
              onClick={() => { setMode('scaffold'); setScaffoldError(null); }}
            />
            <ModeCard
              icon="ti-git-merge"
              label="Onboarder un repo"
              desc="Connecter un repo GitLab interne existant"
              active={mode === 'onboard'}
              onClick={() => { setMode('onboard'); setOnboardError(null); }}
            />
            <ModeCard
              icon="ti-cloud-download"
              label="Importer un repo"
              desc="Rapatrier un repo public GitHub / GitLab"
              active={mode === 'import'}
              onClick={() => { setMode('import'); setImportError(null); }}
            />
          </div>

          {/* Form */}
          <div style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 12, padding: 24 }}>
            {mode === 'scaffold' ? (
              <form onSubmit={handleScaffold} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <div className="form-group">
                    <label className="form-label">Nom de l'application <span style={{ color: 'var(--red)' }}>*</span></label>
                    <input
                      className="form-input"
                      placeholder="mon-service"
                      value={scaffoldForm.name}
                      onChange={e => setScaffoldForm(f => ({ ...f, name: e.target.value }))}
                      required
                      autoFocus
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Responsable</label>
                    <input
                      className="form-input"
                      value={owner}
                      readOnly
                      style={{ color: 'var(--text-muted)', cursor: 'default' }}
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Template <span style={{ color: 'var(--red)' }}>*</span></label>
                  {templatesErr ? (
                    <div className="alert error" style={{ margin: 0 }}>
                      <i className="ti ti-alert-circle" aria-hidden="true" />
                      Impossible de charger les templates
                    </div>
                  ) : (
                    <select
                      className="form-select"
                      value={scaffoldForm.template}
                      onChange={e => setScaffoldForm(f => ({ ...f, template: e.target.value }))}
                      required
                      disabled={templatesLoading}
                    >
                      <option value="">{templatesLoading ? 'Chargement…' : 'Choisir un template'}</option>
                      {templates.map((t: AppTemplate) => (
                        <option key={t.path} value={t.path}>{t.name}</option>
                      ))}
                    </select>
                  )}
                  <span className="form-hint">Template hébergé dans l'espace templates CNP</span>
                </div>

                <div style={{ height: 1, background: 'var(--border)' }} />

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <div className="form-group">
                    <label className="form-label">Port applicatif</label>
                    <input
                      className="form-input"
                      type="number"
                      min={1}
                      max={65535}
                      value={scaffoldForm.port}
                      onChange={e => setScaffoldForm(f => ({ ...f, port: e.target.value }))}
                    />
                    <span className="form-hint">Port exposé par le conteneur</span>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Replicas</label>
                    <input
                      className="form-input"
                      type="number"
                      min={1}
                      max={20}
                      value={scaffoldForm.replicas}
                      onChange={e => setScaffoldForm(f => ({ ...f, replicas: e.target.value }))}
                    />
                    <span className="form-hint">Nombre de pods initiaux</span>
                  </div>
                </div>

                {scaffoldError && (
                  <div className="alert error">
                    <i className="ti ti-alert-circle" aria-hidden="true" />
                    {scaffoldError}
                  </div>
                )}

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 4 }}>
                  <button type="button" className="btn btn-ghost" onClick={() => navigate('/resources')} disabled={scaffoldMutation.isPending}>
                    Annuler
                  </button>
                  <button type="submit" className="btn btn-primary" disabled={scaffoldMutation.isPending || !scaffoldForm.template}>
                    {scaffoldMutation.isPending ? (
                      <>
                        <i className="ti ti-loader-2" aria-hidden="true" style={{ animation: 'spin 1s linear infinite' }} />
                        Scaffolding…
                      </>
                    ) : (
                      <>
                        <i className="ti ti-template" aria-hidden="true" />
                        Créer l'application
                      </>
                    )}
                  </button>
                </div>
              </form>
            ) : mode === 'onboard' ? (
              <form onSubmit={handleOnboard} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <div className="form-group">
                    <label className="form-label">Nom de l'application <span style={{ color: 'var(--red)' }}>*</span></label>
                    <input
                      className="form-input"
                      placeholder="mon-service"
                      value={onboardForm.name}
                      onChange={e => setOnboardForm(f => ({ ...f, name: e.target.value }))}
                      required
                      autoFocus
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Responsable</label>
                    <input
                      className="form-input"
                      value={owner}
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
                    value={onboardForm.repo_url}
                    onChange={e => setOnboardForm(f => ({ ...f, repo_url: e.target.value }))}
                    required
                  />
                  <span className="form-hint">Doit être accessible par le bot CNP</span>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <div className="form-group">
                    <label className="form-label">Framework</label>
                    <select
                      className="form-select"
                      value={onboardForm.framework}
                      onChange={e => setOnboardForm(f => ({ ...f, framework: e.target.value }))}
                    >
                      <option value="">Auto-détection</option>
                      <option value="python">Python</option>
                      <option value="generic">Generic</option>
                    </select>
                    <span className="form-hint">Laissez vide pour détection auto</span>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Cluster cible</label>
                    <select
                      className="form-select"
                      value={onboardForm.target_cluster_id}
                      onChange={e => setOnboardForm(f => ({ ...f, target_cluster_id: e.target.value }))}
                    >
                      <option value="">Aucun (à définir plus tard)</option>
                      {clusters.map(c => (
                        <option key={c.id} value={c.id}>{c.name}</option>
                      ))}
                    </select>
                    <span className="form-hint">Optionnel</span>
                  </div>
                </div>

                {onboardError && (
                  <div className="alert error">
                    <i className="ti ti-alert-circle" aria-hidden="true" />
                    {onboardError}
                  </div>
                )}

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 4 }}>
                  <button type="button" className="btn btn-ghost" onClick={() => navigate('/resources')} disabled={onboardMutation.isPending}>
                    Annuler
                  </button>
                  <button type="submit" className="btn btn-primary" disabled={onboardMutation.isPending}>
                    {onboardMutation.isPending ? (
                      <>
                        <i className="ti ti-loader-2" aria-hidden="true" style={{ animation: 'spin 1s linear infinite' }} />
                        Onboarding…
                      </>
                    ) : (
                      <>
                        <i className="ti ti-git-merge" aria-hidden="true" />
                        Onboarder
                      </>
                    )}
                  </button>
                </div>
              </form>
            ) : (
              <form onSubmit={handleImport} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
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
                      value={owner}
                      readOnly
                      style={{ color: 'var(--text-muted)', cursor: 'default' }}
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">URL source publique <span style={{ color: 'var(--red)' }}>*</span></label>
                  <input
                    className="form-input mono"
                    placeholder="https://github.com/tiangolo/fastapi"
                    value={importForm.source_url}
                    onChange={e => setImportForm(f => ({ ...f, source_url: e.target.value }))}
                    required
                  />
                  <span className="form-hint">GitHub ou GitLab public — le repo sera cloné dans cnp-apps</span>
                </div>

                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', userSelect: 'none' }}>
                  <input
                    type="checkbox"
                    checked={importForm.raw}
                    onChange={e => setImportForm(f => ({ ...f, raw: e.target.checked }))}
                  />
                  <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                    Importer tel quel <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>(sans injection CI)</span>
                  </span>
                </label>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
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
                    <span className="form-hint">Laissez vide pour détection auto</span>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Cluster cible</label>
                    <select
                      className="form-select"
                      value={importForm.target_cluster_id}
                      onChange={e => setImportForm(f => ({ ...f, target_cluster_id: e.target.value }))}
                    >
                      <option value="">Aucun (à définir plus tard)</option>
                      {clusters.map(c => (
                        <option key={c.id} value={c.id}>{c.name}</option>
                      ))}
                    </select>
                    <span className="form-hint">Optionnel</span>
                  </div>
                </div>

                {importError && (
                  <div className="alert error">
                    <i className="ti ti-alert-circle" aria-hidden="true" />
                    {importError}
                  </div>
                )}

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 4 }}>
                  <button type="button" className="btn btn-ghost" onClick={() => navigate('/resources')} disabled={importMutation.isPending}>
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
                        <i className="ti ti-cloud-download" aria-hidden="true" />
                        Importer
                      </>
                    )}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      </div>
    </>
  );
};

function ModeCard({ icon, label, desc, active, onClick }: {
  icon: string;
  label: string;
  desc: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-start',
        gap: 8,
        padding: '16px 18px',
        borderRadius: 12,
        border: `1.5px solid ${active ? 'var(--accent)' : 'var(--border-strong)'}`,
        background: active ? 'rgba(26,107,240,0.04)' : 'var(--bg-surface)',
        cursor: 'pointer',
        textAlign: 'left',
        transition: 'border-color 0.15s, background 0.15s',
        fontFamily: 'var(--font)',
      }}
    >
      <div style={{
        width: 34,
        height: 34,
        borderRadius: 9,
        background: active ? 'rgba(26,107,240,0.10)' : 'var(--bg-base)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        transition: 'background 0.15s',
      }}>
        <i className={`ti ${icon}`} style={{ fontSize: 16, color: active ? 'var(--accent)' : 'var(--text-muted)' }} aria-hidden="true" />
      </div>
      <div>
        <div style={{ fontSize: 13, fontWeight: 600, color: active ? 'var(--text-primary)' : 'var(--text-secondary)', marginBottom: 2 }}>
          {label}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.4 }}>
          {desc}
        </div>
      </div>
      {active && (
        <div style={{ position: 'absolute', top: 12, right: 12 }}>
          <i className="ti ti-check" style={{ fontSize: 13, color: 'var(--accent)' }} aria-hidden="true" />
        </div>
      )}
    </button>
  );
}
