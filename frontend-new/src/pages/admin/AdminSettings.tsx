import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { IconEye, IconEyeOff, IconRefresh } from '@tabler/icons-react';
import { useScopeStore } from '@/store/scope';
import { useBreadcrumb } from '@/components/nav/BreadcrumbContext';
import { gitlabApi } from '@/api/gitlab';
import { clustersApi } from '@/api/clusters';
import { assistantApi } from '@/api/assistant';
import { appsApi } from '@/api/apps';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Select } from '@/components/ui/Select';
import { InfoPopover } from '@/components/ui/InfoPopover';

const PROVIDER_INFO: Record<
  string,
  { label: string; juridiction: string; risque: string; avantages: string }
> = {
  mock: {
    label: 'Mock (local)',
    juridiction: 'Local',
    risque: 'Aucune donnée ne sort de la CNP.',
    avantages: 'Gratuit, pour tests/démo — aucune vraie capacité IA.',
  },
  mistral: {
    label: 'Mistral (UE / France)',
    juridiction: 'Union Européenne',
    risque: 'Souverain, RGPD, hors CLOUD Act US.',
    avantages: 'Meilleure protection des données. Coût moyen.',
  },
  gemini: {
    label: 'Gemini (Google, US)',
    juridiction: 'États-Unis',
    risque: 'Soumis au CLOUD Act US, données hors UE.',
    avantages: 'Bon rapport qualité, free tier généreux.',
  },
  deepseek: {
    label: 'DeepSeek (Chine)',
    juridiction: 'Chine',
    risque:
      'Aucune garantie de protection des données (risque de vol / accès État). À réserver au metadata_only non sensible.',
    avantages: 'Le moins cher, meilleur rapport perf/prix.',
  },
};

export function AdminSettings() {
  const { setScope } = useScopeStore();
  const { setBreadcrumb } = useBreadcrumb();
  useEffect(() => { setScope('admin'); }, [setScope]);

  useEffect(() => {
    setBreadcrumb([{ label: 'Platform', to: '/admin/clusters' }, { label: 'Settings' }]);
    return () => setBreadcrumb([]);
  }, [setBreadcrumb]);

  const [platformName, setPlatformName] = useState('Cloud Native Platform');
  const [publicUrl, setPublicUrl] = useState('');
  const [gitlabUrl, setGitlabUrl] = useState('');
  const [gitlabGroup, setGitlabGroup] = useState('');
  const [gitlabToken, setGitlabToken] = useState('');
  const [tokenVisible, setTokenVisible] = useState(false);
  const [gitlabConnected, setGitlabConnected] = useState<boolean | null>(null);

  const [clusterName, setClusterName] = useState('');
  const [clusterEndpoint, setClusterEndpoint] = useState('');
  const [kubeconfig, setKubeconfig] = useState('');

  const [kubeconfigVisible, setKubeconfigVisible] = useState(false);

  const healthMutation = useMutation({
    mutationFn: gitlabApi.healthcheck,
    onSuccess: (data) => setGitlabConnected(data.connected),
    onError: () => setGitlabConnected(false),
  });

  const saveGitlabMutation = useMutation({
    mutationFn: () => gitlabApi.saveCredentials(gitlabToken, gitlabGroup),
    onSuccess: () => setGitlabToken(''),
  });

  const registerClusterMutation = useMutation({
    mutationFn: () =>
      clustersApi.register({
        name: clusterName,
        endpoint: clusterEndpoint,
        kubeconfig,
      }),
    onSuccess: () => {
      setClusterName('');
      setClusterEndpoint('');
      setKubeconfig('');
    },
  });

  // ── Assistant IA (réglages globaux) ─────────────────────────────────────────
  const qc = useQueryClient();
  const { data: aiSettings } = useQuery({
    queryKey: ['ai-global-settings'],
    queryFn: assistantApi.getGlobalSettings,
    retry: false,
  });
  const { data: apps } = useQuery({ queryKey: ['apps-list'], queryFn: appsApi.list });

  const [platformAccess, setPlatformAccess] = useState(false);
  const [appAccess, setAppAccess] = useState(false);
  const [allowedAppIds, setAllowedAppIds] = useState<number[]>([]);
  const [aiProvider, setAiProvider] = useState('mock');
  const [aiModel, setAiModel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [apiKeyVisible, setApiKeyVisible] = useState(false);
  const [apiKeyDirty, setApiKeyDirty] = useState(false);

  useEffect(() => {
    if (!aiSettings) return;
    setPlatformAccess(aiSettings.platform_data_access_enabled);
    setAppAccess(aiSettings.app_data_access_enabled);
    setAllowedAppIds(aiSettings.allowed_app_ids ?? []);
    setAiProvider(aiSettings.provider || 'mock');
    setAiModel(aiSettings.model || '');
  }, [aiSettings]);

  const saveAiMutation = useMutation({
    mutationFn: () =>
      assistantApi.patchGlobalSettings({
        platform_data_access_enabled: platformAccess,
        app_data_access_enabled: appAccess,
        allowed_app_ids: allowedAppIds,
        provider: aiProvider,
        model: aiModel,
        ...(apiKeyDirty ? { api_key: apiKey } : {}),
      }),
    onSuccess: () => {
      setApiKey('');
      setApiKeyDirty(false);
      qc.invalidateQueries({ queryKey: ['ai-global-settings'] });
    },
  });

  function toggleAllowedApp(id: number) {
    setAllowedAppIds((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));
  }

  return (
    <div className="max-w-[1440px] mx-auto px-8 py-6">
      <h1 className="text-xl font-semibold text-foreground mb-6">Platform settings</h1>
      <div className="max-w-2xl flex flex-col gap-6">

      {/* Global params */}
      <Card>
        <h2 className="text-sm font-medium text-foreground mb-4">Global settings</h2>
        <div className="flex flex-col gap-3">
          <Input
            label="Platform name"
            value={platformName}
            onChange={(e) => setPlatformName(e.target.value)}
          />
          <Input
            label="Public URL"
            value={publicUrl}
            onChange={(e) => setPublicUrl(e.target.value)}
            placeholder="https://cnp.example.com"
          />
          <div className="flex justify-end">
            <Button variant="primary" size="sm">Save</Button>
          </div>
        </div>
      </Card>

      {/* Assistant IA */}
      <Card>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium text-foreground">Assistant IA</h2>
          {aiSettings && <Badge variant="muted">source&nbsp;: {aiSettings.source}</Badge>}
        </div>
        <div className="flex flex-col gap-4">
          <label className="flex items-start gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={platformAccess}
              onChange={(e) => setPlatformAccess(e.target.checked)}
              className="mt-0.5"
            />
            <span>
              <span className="font-medium text-foreground">Accès aux données de la CNP</span>
              <span className="block text-xs text-muted-foreground">
                Autorise l’assistant à répondre à partir de la documentation et des données de la plateforme.
              </span>
            </span>
          </label>

          <label className="flex items-start gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={appAccess}
              onChange={(e) => setAppAccess(e.target.checked)}
              className="mt-0.5"
            />
            <span>
              <span className="font-medium text-foreground">
                Accès aux données d’une application / repo GitLab
              </span>
              <span className="block text-xs text-muted-foreground">
                Autorise l’assistant à lire les métadonnées des applications sélectionnées (selon les permissions de l’utilisateur).
              </span>
            </span>
          </label>

          {appAccess && (
            <div className="ml-6 border border-border rounded-md p-2 max-h-40 overflow-y-auto">
              {(apps ?? []).length === 0 && (
                <p className="text-xs text-muted-foreground">Aucune application.</p>
              )}
              {(apps ?? []).map((a) => (
                <label key={a.id} className="flex items-center gap-2 text-sm py-0.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={allowedAppIds.includes(a.id)}
                    onChange={() => toggleAllowedApp(a.id)}
                  />
                  <span className="truncate">
                    {a.name} <span className="text-xs text-muted-foreground">({a.slug})</span>
                  </span>
                </label>
              ))}
              <p className="text-xs text-muted-foreground mt-1">
                Sélectionnez les applications autorisées. Aucune sélection = aucune application accessible à l’assistant.
              </p>
            </div>
          )}

          <div>
            <div className="flex items-center gap-1.5 mb-1">
              <span className="text-sm font-medium text-foreground">Provider IA (souveraineté)</span>
              <InfoPopover>
                <p className="font-medium mb-2">Souveraineté des providers</p>
                <ul className="space-y-2">
                  {Object.values(PROVIDER_INFO).map((p) => (
                    <li key={p.label}>
                      <span className="font-medium">{p.label}</span>{' '}
                      <span className="text-muted-foreground">— {p.juridiction}</span>
                      <span className="block">Risque : {p.risque}</span>
                      <span className="block">Avantages : {p.avantages}</span>
                    </li>
                  ))}
                </ul>
              </InfoPopover>
            </div>
            <Select
              options={Object.entries(PROVIDER_INFO).map(([value, m]) => ({ value, label: m.label }))}
              value={aiProvider}
              onChange={setAiProvider}
            />
            {aiProvider === 'deepseek' && (
              <p className="text-xs text-danger mt-1">
                ⚠️ DeepSeek (Chine) : aucune garantie de protection des données. À réserver au metadata_only non sensible.
              </p>
            )}
          </div>

          <Input
            label="Modèle"
            value={aiModel}
            onChange={(e) => setAiModel(e.target.value)}
            placeholder="ex : mistral-small-latest, gemini-flash-latest, deepseek-v4-flash"
            mono
          />

          <Input
            label={`Clé API${aiSettings?.api_key_set ? ' (définie)' : ''}`}
            value={apiKeyVisible ? apiKey : apiKey ? '••••••••••••••••' : ''}
            onChange={(e) => {
              setApiKey(e.target.value);
              setApiKeyDirty(true);
            }}
            type={apiKeyVisible ? 'text' : 'password'}
            mono
            placeholder={
              aiSettings?.api_key_set ? 'Clé enregistrée — saisir pour remplacer' : 'Coller la clé API'
            }
            suffix={
              <button
                type="button"
                onClick={() => setApiKeyVisible((v) => !v)}
                className="text-muted-foreground"
              >
                {apiKeyVisible ? <IconEyeOff size={13} /> : <IconEye size={13} />}
              </button>
            }
          />

          <div className="flex justify-end">
            <Button
              variant="primary"
              size="sm"
              loading={saveAiMutation.isPending}
              onClick={() => saveAiMutation.mutate()}
            >
              Save
            </Button>
          </div>
        </div>
      </Card>

      {/* GitLab connection */}
      <Card>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium text-foreground">GitLab connection</h2>
          {gitlabConnected === true && <Badge variant="success">Connected</Badge>}
          {gitlabConnected === false && <Badge variant="danger">Disconnected</Badge>}
          {gitlabConnected === null && <Badge variant="muted">Not verified</Badge>}
        </div>
        <div className="flex flex-col gap-3">
          <Input
            label="GitLab instance URL"
            value={gitlabUrl}
            onChange={(e) => setGitlabUrl(e.target.value)}
            placeholder="https://gitlab.example.com"
          />
          <Input
            label="Root group"
            value={gitlabGroup}
            onChange={(e) => setGitlabGroup(e.target.value)}
            placeholder="cnp-apps"
          />
          <Input
            label="Token service account"
            value={tokenVisible ? gitlabToken : gitlabToken ? '••••••••••••••••' : ''}
            onChange={(e) => setGitlabToken(e.target.value)}
            type={tokenVisible ? 'text' : 'password'}
            mono
            suffix={
              <button
                type="button"
                onClick={() => setTokenVisible((v) => !v)}
                className="text-muted-foreground"
              >
                {tokenVisible ? <IconEyeOff size={13} /> : <IconEye size={13} />}
              </button>
            }
          />
          <div className="flex gap-2 justify-end">
            <Button
              variant="secondary"
              size="sm"
              icon={<IconRefresh size={13} />}
              loading={healthMutation.isPending}
              onClick={() => healthMutation.mutate()}
            >
              Test connection
            </Button>
            <Button
              variant="primary"
              size="sm"
              loading={saveGitlabMutation.isPending}
              disabled={!gitlabToken || !gitlabGroup}
              onClick={() => saveGitlabMutation.mutate()}
            >
              Save
            </Button>
          </div>
        </div>
      </Card>

      {/* Register cluster */}
      <Card>
        <h2 className="text-sm font-medium text-foreground mb-4">Register cluster</h2>
        <div className="flex flex-col gap-3">
          <Input
            label="Name"
            value={clusterName}
            onChange={(e) => setClusterName(e.target.value)}
            placeholder="cnp-prod"
          />
          <Input
            label="Endpoint API"
            value={clusterEndpoint}
            onChange={(e) => setClusterEndpoint(e.target.value)}
            placeholder="https://k8s.example.com:6443"
            mono
          />
          <div>
            <label className="text-sm font-medium text-foreground block mb-1">
              Kubeconfig
            </label>
            <textarea
              value={kubeconfigVisible ? kubeconfig : kubeconfig ? '••••••\n••••••\n••••••' : ''}
              onChange={(e) => setKubeconfig(e.target.value)}
              onFocus={() => setKubeconfigVisible(true)}
              onBlur={() => setKubeconfigVisible(false)}
              rows={5}
              placeholder="Paste kubeconfig content…"
              className="w-full px-3 py-2 text-xs font-mono rounded-md border border-input bg-background resize-none focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <p className="text-xs text-muted-foreground mt-1">
              Kubeconfig is stored encrypted. Only the active context is used.
            </p>
          </div>
          <div className="flex justify-end">
            <Button
              variant="primary"
              size="sm"
              loading={registerClusterMutation.isPending}
              disabled={!clusterName || !clusterEndpoint || !kubeconfig}
              onClick={() => registerClusterMutation.mutate()}
            >
              Register cluster
            </Button>
          </div>
        </div>
      </Card>
      </div>
    </div>
  );
}
