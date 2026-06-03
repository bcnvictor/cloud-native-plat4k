import { useState, FormEvent } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { credentialsApi } from '@/api/credentials';
import { gitlabApi, GitLabHealthcheck } from '@/api/gitlab';
import { CloudType } from '@/types';
import { SettingsLayout } from '@/components/SettingsLayout';

const GITLAB_PAT_URL = 'https://gitlab.com/-/user_settings/personal_access_tokens';

export const Credentials = () => {
  const queryClient = useQueryClient();

  const [isAdding, setIsAdding] = useState(false);
  const [cloud, setCloud] = useState<CloudType>('aws');
  const [creds, setCreds] = useState('');
  const [credsError, setCredsError] = useState('');

  const [pat, setPat] = useState('');
  const [namespace, setNamespace] = useState('');
  const [showPat, setShowPat] = useState(false);
  const [healthcheck, setHealthcheck] = useState<GitLabHealthcheck | null>(null);
  const [isCheckingHealth, setIsCheckingHealth] = useState(false);

  const { data: credentials = [], isLoading } = useQuery({
    queryKey: ['credentials'],
    queryFn: () => credentialsApi.list(),
  });

  const { data: gitlabCred, isLoading: isLoadingGitlab } = useQuery({
    queryKey: ['gitlab-credentials'],
    queryFn: () => gitlabApi.getCredentials(),
  });

  const addCloudMutation = useMutation({
    mutationFn: (data: { cloud: CloudType; credentials: Record<string, string> }) =>
      credentialsApi.add(data.cloud, data.credentials),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['credentials'] });
      setIsAdding(false);
      setCreds('');
      setCredsError('');
    },
  });

  const deleteCloudMutation = useMutation({
    mutationFn: (id: number) => credentialsApi.delete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['credentials'] }),
  });

  const saveGitlabMutation = useMutation({
    mutationFn: () => gitlabApi.saveCredentials(pat.trim(), namespace.trim()),
    onSuccess: async () => {
      queryClient.invalidateQueries({ queryKey: ['gitlab-credentials'] });
      setPat('');
      const result = await gitlabApi.healthcheck();
      setHealthcheck(result);
    },
  });

  const deleteGitlabMutation = useMutation({
    mutationFn: () => gitlabApi.deleteCredentials(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['gitlab-credentials'] });
      setHealthcheck(null);
    },
  });

  const runHealthcheck = async () => {
    setIsCheckingHealth(true);
    try {
      const result = await gitlabApi.healthcheck();
      setHealthcheck(result);
    } finally {
      setIsCheckingHealth(false);
    }
  };

  const handleAddCloud = (e: FormEvent) => {
    e.preventDefault();
    setCredsError('');
    try {
      const parsedCreds = JSON.parse(creds);
      addCloudMutation.mutate({ cloud, credentials: parsedCreds });
    } catch {
      setCredsError('Format JSON invalide');
    }
  };

  const handleSaveGitlab = (e: FormEvent) => {
    e.preventDefault();
    if (!namespace.trim()) return;
    saveGitlabMutation.mutate();
  };

  return (
    <SettingsLayout
      title="Cloud & GitLab"
      description="Gérez vos accès cloud et votre compte GitLab EPITA."
    >
      {/* ── Cloud Credentials ── */}
      <div className="card">
        <div className="card-header">
          Credentials Cloud
          <button className="btn btn-primary btn-sm" onClick={() => setIsAdding(v => !v)}>
            <i className="ti ti-plus" aria-hidden="true" />Ajouter
          </button>
        </div>

        {isAdding && (
          <div style={{ padding: '16px', borderBottom: '1px solid var(--border)' }}>
            <form onSubmit={handleAddCloud} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div className="form-group">
                <label className="form-label">Fournisseur cloud</label>
                <select className="form-select" value={cloud} onChange={e => setCloud(e.target.value as CloudType)}>
                  <option value="aws">AWS</option>
                  <option value="gcp">GCP</option>
                  <option value="openstack">OpenStack</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Credentials (JSON)</label>
                <textarea
                  className="form-textarea"
                  rows={4}
                  value={creds}
                  onChange={e => setCreds(e.target.value)}
                  placeholder='{"aws_access_key_id": "...", "aws_secret_access_key": "..."}'
                />
                {credsError && <span className="form-error">{credsError}</span>}
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => setIsAdding(false)}>Annuler</button>
                <button type="submit" className="btn btn-primary btn-sm" disabled={addCloudMutation.isPending}>
                  {addCloudMutation.isPending ? 'Sauvegarde…' : 'Sauvegarder'}
                </button>
              </div>
            </form>
          </div>
        )}

        {isLoading ? (
          <div className="loading-state" style={{ padding: '24px' }}>Chargement…</div>
        ) : credentials.length === 0 && !isAdding ? (
          <div style={{ padding: '20px 16px', fontSize: 12, color: 'var(--text-muted)', textAlign: 'center' }}>
            Aucun credential cloud configuré.
          </div>
        ) : (
          credentials.map(cred => (
            <div key={cred.id} className="kv-row">
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <i className="ti ti-cloud" style={{ color: 'var(--text-muted)', fontSize: 15 }} aria-hidden="true" />
                <div>
                  <span className={`env-tag ${cred.cloud}`} style={{ marginRight: 8 }}>{cred.cloud.toUpperCase()}</span>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                    Ajouté le {new Date(cred.created_at).toLocaleDateString('fr-FR')}
                  </span>
                </div>
              </div>
              <button
                className="btn-icon"
                style={{ width: 24, height: 24 }}
                onClick={() => deleteCloudMutation.mutate(cred.id)}
                disabled={deleteCloudMutation.isPending}
                title="Supprimer"
              >
                <i className="ti ti-trash" style={{ fontSize: 13 }} aria-hidden="true" />
              </button>
            </div>
          ))
        )}
      </div>

      {/* ── GitLab ── */}
      <div className="card">
        <div className="card-header" style={{ justifyContent: 'space-between' }}>
          <span>GitLab EPITA</span>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {gitlabCred?.configured && (
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => deleteGitlabMutation.mutate()}
                disabled={deleteGitlabMutation.isPending}
                style={{ color: 'var(--red)', borderColor: 'rgba(239,68,68,0.25)' }}
              >
                <i className="ti ti-trash" aria-hidden="true" />Déconnecter
              </button>
            )}
            <a
              href={GITLAB_PAT_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-ghost btn-sm"
              style={{ textDecoration: 'none' }}
            >
              <i className="ti ti-external-link" aria-hidden="true" />Obtenir un PAT
            </a>
          </div>
        </div>

        {!isLoadingGitlab && gitlabCred?.configured && (
          <div className="kv-row">
            <span className="kv-key">Namespace configuré</span>
            <span className="kv-val accent">{gitlabCred.namespace}</span>
          </div>
        )}

        <div style={{ padding: '16px', borderBottom: '1px solid var(--border)' }}>
          <form onSubmit={handleSaveGitlab} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div className="form-group">
              <label className="form-label">Personal Access Token</label>
              <div className="form-input-wrap">
                <input
                  type={showPat ? 'text' : 'password'}
                  className="form-input mono"
                  value={pat}
                  onChange={e => setPat(e.target.value)}
                  placeholder={gitlabCred?.configured ? '(laisser vide pour ne pas changer)' : 'glpat-xxxxxxxxxxxxxxxxxxxx'}
                />
                <button type="button" className="form-input-action" onClick={() => setShowPat(v => !v)}>
                  <i className={`ti ${showPat ? 'ti-eye-off' : 'ti-eye'}`} aria-hidden="true" />
                </button>
              </div>
              <span className="form-hint">Scopes requis : <code>api</code> <code>write_repository</code></span>
            </div>
            <div className="form-group">
              <label className="form-label">Namespace GitLab</label>
              <input
                type="text"
                className="form-input mono"
                value={namespace}
                onChange={e => setNamespace(e.target.value)}
                placeholder={gitlabCred?.configured ? gitlabCred.namespace : 'mon-groupe-ou-username'}
              />
              <span className="form-hint">Groupe ou username GitLab sous lequel les repos seront créés.</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button
                type="submit"
                className="btn btn-primary btn-sm"
                disabled={saveGitlabMutation.isPending || (!pat.trim() && !gitlabCred?.configured) || !namespace.trim()}
              >
                <i className="ti ti-device-floppy" aria-hidden="true" />
                {saveGitlabMutation.isPending ? 'Sauvegarde…' : 'Sauvegarder'}
              </button>
            </div>
            {saveGitlabMutation.isError && (
              <div className="alert error"><i className="ti ti-alert-circle" aria-hidden="true" />Erreur lors de la sauvegarde.</div>
            )}
          </form>
        </div>

        <div style={{ padding: '16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 2 }}>
              État de la connexion
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
              Vérifie que votre token est valide et actif.
            </div>
          </div>
          <button
            className="btn btn-ghost btn-sm"
            onClick={runHealthcheck}
            disabled={isCheckingHealth || !gitlabCred?.configured}
          >
            <i className={`ti ti-refresh${isCheckingHealth ? ' ti-spin' : ''}`} aria-hidden="true" />
            Tester
          </button>
        </div>

        {healthcheck && (
          <div style={{ padding: '0 16px 16px' }}>
            <HealthBadge {...healthcheck} />
          </div>
        )}

        {!gitlabCred?.configured && !healthcheck && (
          <div style={{ padding: '0 16px 16px', fontSize: 12, color: 'var(--text-muted)', fontStyle: 'italic' }}>
            Configurez d'abord votre token ci-dessus.
          </div>
        )}
      </div>
    </SettingsLayout>
  );
};

function HealthBadge({ status, authenticated_as, detail }: { status: string; authenticated_as?: string; detail?: string }) {
  if (status === 'ok') {
    return (
      <div className="alert success">
        <i className="ti ti-circle-check" aria-hidden="true" />
        Connexion OK — authentifié en tant que <strong style={{ marginLeft: 4 }}>{authenticated_as}</strong>
      </div>
    );
  }
  if (status === 'not_configured') {
    return (
      <div className="alert warn">
        <i className="ti ti-alert-triangle" aria-hidden="true" />
        Aucun token configuré.
      </div>
    );
  }
  return (
    <div className="alert error">
      <i className="ti ti-circle-x" aria-hidden="true" />
      {detail ?? 'Erreur de connexion.'}
    </div>
  );
}
