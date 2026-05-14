import { useState, FormEvent } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { credentialsApi } from '@/api/credentials';
import { gitlabApi, GitLabHealthcheck } from '@/api/gitlab';
import { CloudType } from '@/types';
import {
  Trash2,
  Plus,
  Key,
  GitBranch,
  CheckCircle,
  XCircle,
  AlertCircle,
  ExternalLink,
  RefreshCw,
  Save,
  Eye,
  EyeOff,
} from 'lucide-react';

const GITLAB_PAT_URL = 'https://gitlab.cri.epita.fr/-/user_settings/personal_access_tokens';

export const Credentials = () => {
  const queryClient = useQueryClient();

  // Cloud credentials state
  const [isAdding, setIsAdding] = useState(false);
  const [cloud, setCloud] = useState<CloudType>('aws');
  const [creds, setCreds] = useState('');

  // GitLab form state
  const [pat, setPat] = useState('');
  const [namespace, setNamespace] = useState('');
  const [showPat, setShowPat] = useState(false);
  const [healthcheck, setHealthcheck] = useState<GitLabHealthcheck | null>(null);

  // ── Queries ──────────────────────────────────────────────────────────────

  const { data: credentials, isLoading } = useQuery({
    queryKey: ['credentials'],
    queryFn: () => credentialsApi.list(),
  });

  const { data: gitlabCred, isLoading: isLoadingGitlab } = useQuery({
    queryKey: ['gitlab-credentials'],
    queryFn: () => gitlabApi.getCredentials(),
  });

  // ── Mutations ─────────────────────────────────────────────────────────────

  const addCloudMutation = useMutation({
    mutationFn: (data: { cloud: CloudType; credentials: Record<string, string> }) =>
      credentialsApi.add(data.cloud, data.credentials),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['credentials'] });
      setIsAdding(false);
      setCreds('');
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
      // Auto healthcheck after save
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

  const [isCheckingHealth, setIsCheckingHealth] = useState(false);
  const runHealthcheck = async () => {
    setIsCheckingHealth(true);
    try {
      const result = await gitlabApi.healthcheck();
      setHealthcheck(result);
    } finally {
      setIsCheckingHealth(false);
    }
  };

  // ── Handlers ──────────────────────────────────────────────────────────────

  const handleAddCloud = (e: FormEvent) => {
    e.preventDefault();
    try {
      const parsedCreds = JSON.parse(creds);
      addCloudMutation.mutate({ cloud, credentials: parsedCreds });
    } catch {
      alert('Invalid JSON format for credentials');
    }
  };

  const handleSaveGitlab = (e: FormEvent) => {
    e.preventDefault();
    if (!pat.trim() || !namespace.trim()) return;
    saveGitlabMutation.mutate();
  };

  if (isLoading) return <div>Loading...</div>;

  return (
    <div className="space-y-10">

      {/* ══ Cloud Credentials ══════════════════════════════════════════════ */}
      <div>
        <div className="sm:flex sm:items-center sm:justify-between mb-8">
          <div>
            <h1 className="text-2xl font-semibold text-gray-900">Cloud Credentials</h1>
            <p className="mt-2 text-sm text-gray-700">Manage your access to AWS, GCP, and OpenStack.</p>
          </div>
          <div className="mt-4 sm:mt-0">
            <button
              onClick={() => setIsAdding(!isAdding)}
              className="inline-flex items-center justify-center rounded-md border border-transparent bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700"
            >
              <Plus className="h-4 w-4 mr-2" />
              Add Credentials
            </button>
          </div>
        </div>

        {isAdding && (
          <div className="bg-white shadow sm:rounded-lg mb-8 p-6">
            <h3 className="text-lg leading-6 font-medium text-gray-900">New Credentials</h3>
            <form className="mt-5 space-y-4" onSubmit={handleAddCloud}>
              <div>
                <label className="block text-sm font-medium text-gray-700">Cloud Provider</label>
                <select
                  value={cloud}
                  onChange={(e) => setCloud(e.target.value as CloudType)}
                  className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md"
                >
                  <option value="aws">AWS</option>
                  <option value="gcp">GCP</option>
                  <option value="openstack">OpenStack</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Credentials (JSON)</label>
                <textarea
                  rows={4}
                  value={creds}
                  onChange={(e) => setCreds(e.target.value)}
                  placeholder='{"aws_access_key_id": "...", "aws_secret_access_key": "..."}'
                  className="mt-1 block w-full shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm border border-gray-300 rounded-md font-mono"
                />
              </div>
              <div className="flex justify-end gap-3">
                <button type="button" onClick={() => setIsAdding(false)} className="bg-white py-2 px-4 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 hover:bg-gray-50">
                  Cancel
                </button>
                <button type="submit" disabled={addCloudMutation.isPending} className="inline-flex justify-center py-2 px-4 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50">
                  Save
                </button>
              </div>
            </form>
          </div>
        )}

        <div className="bg-white shadow overflow-hidden sm:rounded-md">
          <ul className="divide-y divide-gray-200">
            {credentials?.map((cred) => (
              <li key={cred.id}>
                <div className="px-4 py-4 flex items-center sm:px-6">
                  <div className="min-w-0 flex-1 sm:flex sm:items-center sm:justify-between">
                    <div className="flex items-center">
                      <Key className="h-6 w-6 text-gray-400" />
                      <div className="ml-4">
                        <h4 className="text-lg font-bold text-blue-600 uppercase">{cred.cloud}</h4>
                        <p className="mt-1 text-sm text-gray-500">Added on {new Date(cred.created_at).toLocaleDateString()}</p>
                      </div>
                    </div>
                  </div>
                  <button onClick={() => deleteCloudMutation.mutate(cred.id)} className="ml-5 p-2 text-red-600 hover:text-red-900 rounded-md hover:bg-red-50">
                    <Trash2 className="h-5 w-5" />
                  </button>
                </div>
              </li>
            ))}
            {credentials?.length === 0 && (
              <li className="px-4 py-8 text-center text-gray-500">No credentials configured.</li>
            )}
          </ul>
        </div>
      </div>

      {/* ══ GitLab EPITA ═══════════════════════════════════════════════════ */}
      <div>
        <div className="mb-6">
          <h2 className="text-2xl font-semibold text-gray-900 flex items-center gap-2">
            <GitBranch className="h-6 w-6 text-orange-500" />
            GitLab EPITA
          </h2>
          <p className="mt-2 text-sm text-gray-700">
            Connectez votre compte{' '}
            <a href="https://gitlab.cri.epita.fr" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">
              gitlab.cri.epita.fr
            </a>{' '}
            en renseignant votre Personal Access Token.
          </p>
        </div>

        <div className="bg-white shadow sm:rounded-lg divide-y divide-gray-200">

          {/* ── PAT Form ── */}
          <div className="p-6">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="text-base font-medium text-gray-900">Personal Access Token</h3>
                {!isLoadingGitlab && gitlabCred?.configured && (
                  <p className="mt-1 text-sm text-gray-500">
                    Namespace configuré : <span className="font-mono font-medium text-gray-800">{gitlabCred.namespace}</span>
                  </p>
                )}
              </div>
              <div className="flex items-center gap-2">
                {gitlabCred?.configured && (
                  <button
                    onClick={() => deleteGitlabMutation.mutate()}
                    disabled={deleteGitlabMutation.isPending}
                    className="p-2 text-red-500 hover:text-red-700 hover:bg-red-50 rounded-md"
                    title="Supprimer le token"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                )}
                <a
                  href={GITLAB_PAT_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-sm text-blue-600 hover:underline"
                >
                  Obtenir un PAT
                  <ExternalLink className="h-3.5 w-3.5" />
                </a>
              </div>
            </div>

            <form onSubmit={handleSaveGitlab} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">Token</label>
                <div className="mt-1 relative">
                  <input
                    type={showPat ? 'text' : 'password'}
                    value={pat}
                    onChange={(e) => setPat(e.target.value)}
                    placeholder={gitlabCred?.configured ? '••••••••••••••••••••• (laisser vide pour ne pas changer)' : 'votre-personal-access-token'}
                    className="block w-full pr-10 shadow-sm focus:ring-orange-500 focus:border-orange-500 sm:text-sm border border-gray-300 rounded-md py-2 px-3 font-mono"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPat(!showPat)}
                    className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600"
                  >
                    {showPat ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                <p className="mt-1 text-xs text-gray-500">
                  Scopes requis :{' '}
                  <code className="bg-orange-100 text-orange-800 px-1 rounded">api</code>{' '}
                  <code className="bg-orange-100 text-orange-800 px-1 rounded">write_repository</code>
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700">Namespace GitLab</label>
                <input
                  type="text"
                  value={namespace}
                  onChange={(e) => setNamespace(e.target.value)}
                  placeholder={gitlabCred?.configured ? gitlabCred.namespace : 'mon-groupe-ou-username'}
                  className="mt-1 block w-full shadow-sm focus:ring-orange-500 focus:border-orange-500 sm:text-sm border border-gray-300 rounded-md py-2 px-3 font-mono"
                />
                <p className="mt-1 text-xs text-gray-500">
                  Groupe ou username GitLab sous lequel les repos seront créés.
                </p>
              </div>

              <div className="flex items-center justify-between pt-1">
                <div>
                  {saveGitlabMutation.isError && (
                    <p className="text-sm text-red-600">Erreur lors de la sauvegarde.</p>
                  )}
                </div>
                <button
                  type="submit"
                  disabled={saveGitlabMutation.isPending || (!pat.trim() && !gitlabCred?.configured) || !namespace.trim()}
                  className="inline-flex items-center gap-2 px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-orange-600 hover:bg-orange-700 disabled:opacity-50"
                >
                  <Save className="h-4 w-4" />
                  {saveGitlabMutation.isPending ? 'Sauvegarde...' : 'Sauvegarder'}
                </button>
              </div>
            </form>
          </div>

          {/* ── Healthcheck ── */}
          <div className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-base font-medium text-gray-900">État de la connexion</h3>
                <p className="mt-1 text-sm text-gray-500">Vérifie que votre token est valide et actif.</p>
              </div>
              <button
                onClick={runHealthcheck}
                disabled={isCheckingHealth || !gitlabCred?.configured}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-md border border-gray-300 bg-white text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-40"
              >
                <RefreshCw className={`h-4 w-4 ${isCheckingHealth ? 'animate-spin' : ''}`} />
                Tester
              </button>
            </div>

            {healthcheck && (
              <div className="mt-4">
                <HealthcheckBadge {...healthcheck} />
              </div>
            )}

            {!gitlabCred?.configured && !healthcheck && (
              <p className="mt-3 text-sm text-gray-400 italic">Configurez d'abord votre token ci-dessus.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

// ── Sub-components ────────────────────────────────────────────────────────────

function HealthcheckBadge({ status, authenticated_as, detail }: { status: string; authenticated_as?: string; detail?: string }) {
  if (status === 'ok') {
    return (
      <div className="flex items-center gap-2 text-green-700 bg-green-50 border border-green-200 rounded-md px-4 py-3">
        <CheckCircle className="h-5 w-5 flex-shrink-0" />
        <span className="text-sm font-medium">
          Connexion OK — authentifié en tant que <strong>{authenticated_as}</strong>
        </span>
      </div>
    );
  }
  if (status === 'not_configured') {
    return (
      <div className="flex items-center gap-2 text-yellow-700 bg-yellow-50 border border-yellow-200 rounded-md px-4 py-3">
        <AlertCircle className="h-5 w-5 flex-shrink-0" />
        <span className="text-sm">Aucun token configuré.</span>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2 text-red-700 bg-red-50 border border-red-200 rounded-md px-4 py-3">
      <XCircle className="h-5 w-5 flex-shrink-0" />
      <span className="text-sm">{detail ?? 'Erreur de connexion.'}</span>
    </div>
  );
}
