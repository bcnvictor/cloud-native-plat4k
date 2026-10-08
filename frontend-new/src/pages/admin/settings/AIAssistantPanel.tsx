import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { IconEye, IconEyeOff } from '@tabler/icons-react';
import { assistantApi } from '@/api/assistant';
import { appsApi } from '@/api/apps';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Select } from '@/components/ui/Select';
import { InfoPopover } from '@/components/ui/InfoPopover';
import { toast } from '@/components/ui/toast';
import { apiError } from '@/utils/apiError';
import { CONFIG_ACTIONS, ConfigHistory } from './ConfigHistory';

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

export function AIAssistantPanel() {
  const qc = useQueryClient();
  const { data: aiSettings } = useQuery({
    queryKey: ['ai-global-settings'],
    queryFn: assistantApi.getGlobalSettings,
    retry: false,
  });
  const { data: apps } = useQuery({ queryKey: ['apps-list'], queryFn: appsApi.list });

  const [aiEnabled, setAiEnabled] = useState(false);
  const [graphicalBotEnabled, setGraphicalBotEnabled] = useState(true);
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
    setAiEnabled(aiSettings.assistant_enabled);
    setGraphicalBotEnabled(aiSettings.graphical_bot_enabled);
    setPlatformAccess(aiSettings.platform_data_access_enabled);
    setAppAccess(aiSettings.app_data_access_enabled);
    setAllowedAppIds(aiSettings.allowed_app_ids ?? []);
    setAiProvider(aiSettings.provider || 'mock');
    setAiModel(aiSettings.model || '');
  }, [aiSettings]);

  const saveAiMutation = useMutation({
    mutationFn: () =>
      assistantApi.patchGlobalSettings({
        assistant_enabled: aiEnabled,
        graphical_bot_enabled: graphicalBotEnabled,
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
      qc.invalidateQueries({ queryKey: ['audit-logs'] });
      toast({ title: 'AI assistant settings saved' });
    },
    onError: (err) => toast({ title: 'Save failed', description: apiError(err), variant: 'destructive' }),
  });

  function toggleAllowedApp(id: number) {
    setAllowedAppIds((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));
  }

  return (
    <div className="flex flex-col gap-5">
      <Card>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium text-foreground">Assistant IA</h2>
          {aiSettings && <Badge variant="muted">source&nbsp;: {aiSettings.source}</Badge>}
        </div>
        <div className="flex flex-col gap-4">
          <label className="flex items-start gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={aiEnabled}
              onChange={(e) => setAiEnabled(e.target.checked)}
              className="mt-0.5"
            />
            <span>
              <span className="font-medium text-foreground">Activer l’assistant IA</span>
              <span className="block text-xs text-muted-foreground">
                Active le chatbot sur toute la plateforme. Tant qu’il est désactivé, les
                utilisateurs voient « Assistant IA inactif ».
              </span>
            </span>
          </label>

          <label className="flex items-start gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={graphicalBotEnabled}
              onChange={(e) => setGraphicalBotEnabled(e.target.checked)}
              className="mt-0.5"
            />
            <span>
              <span className="font-medium text-foreground">Afficher le bot graphique</span>
              <span className="block text-xs text-muted-foreground">
                Affiche la mascotte flottante et les avatars du chatbot. Le bouton assistant de la sidebar reste disponible.
              </span>
            </span>
          </label>

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
      <ConfigHistory title="Change history" actions={CONFIG_ACTIONS.ai} />
    </div>
  );
}
