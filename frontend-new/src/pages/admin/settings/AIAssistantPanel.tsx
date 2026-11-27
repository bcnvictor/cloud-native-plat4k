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
    risque: 'No data leaves the CNP.',
    avantages: 'Free, for tests/demo — no real AI capability.',
  },
  mistral: {
    label: 'Mistral (EU / France)',
    juridiction: 'European Union',
    risque: 'Sovereign, GDPR, outside the US CLOUD Act.',
    avantages: 'Best data protection. Medium cost.',
  },
  gemini: {
    label: 'Gemini (Google, US)',
    juridiction: 'United States',
    risque: 'Subject to the US CLOUD Act, data outside the EU.',
    avantages: 'Good value, generous free tier.',
  },
  deepseek: {
    label: 'DeepSeek (China)',
    juridiction: 'China',
    risque:
      'No data protection guarantee (risk of theft / state access). Use only with non-sensitive metadata_only.',
    avantages: 'Cheapest, best price/performance.',
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
          <h2 className="text-sm font-medium text-foreground">Configuration</h2>
          {aiSettings && <Badge variant="muted">source: {aiSettings.source}</Badge>}
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
              <span className="font-medium text-foreground">Enable the AI assistant</span>
              <span className="block text-xs text-muted-foreground">
                Enables the chatbot across the whole platform. While it is disabled,
                users see “AI assistant inactive”.
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
              <span className="font-medium text-foreground">Show the graphical bot</span>
              <span className="block text-xs text-muted-foreground">
                Shows the floating mascot and the chatbot avatars. The assistant button in the sidebar remains available.
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
              <span className="font-medium text-foreground">Access to CNP data</span>
              <span className="block text-xs text-muted-foreground">
                Allows the assistant to answer using the platform documentation and data.
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
                Access to application / GitLab repo data
              </span>
              <span className="block text-xs text-muted-foreground">
                Allows the assistant to read the metadata of the selected applications (according to the user's permissions).
              </span>
            </span>
          </label>

          {appAccess && (
            <div className="ml-6 border border-border rounded-md p-2 max-h-40 overflow-y-auto">
              {(apps ?? []).length === 0 && (
                <p className="text-xs text-muted-foreground">No applications.</p>
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
                Select the allowed applications. No selection = no application accessible to the assistant.
              </p>
            </div>
          )}

          <div>
            <div className="flex items-center gap-1.5 mb-1">
              <span className="text-sm font-medium text-foreground">AI provider (sovereignty)</span>
              <InfoPopover>
                <p className="font-medium mb-2">Provider sovereignty</p>
                <ul className="space-y-2">
                  {Object.values(PROVIDER_INFO).map((p) => (
                    <li key={p.label}>
                      <span className="font-medium">{p.label}</span>{' '}
                      <span className="text-muted-foreground">— {p.juridiction}</span>
                      <span className="block">Risk: {p.risque}</span>
                      <span className="block">Pros: {p.avantages}</span>
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
                ⚠️ DeepSeek (China): no data protection guarantee. Use only with non-sensitive metadata_only.
              </p>
            )}
          </div>

          <Input
            label="Model"
            value={aiModel}
            onChange={(e) => setAiModel(e.target.value)}
            placeholder="e.g. mistral-small-latest, gemini-flash-latest, deepseek-v4-flash"
            mono
          />

          <Input
            label={`API key${aiSettings?.api_key_set ? ' (set)' : ''}`}
            value={apiKeyVisible ? apiKey : apiKey ? '••••••••••••••••' : ''}
            onChange={(e) => {
              setApiKey(e.target.value);
              setApiKeyDirty(true);
            }}
            type={apiKeyVisible ? 'text' : 'password'}
            mono
            placeholder={
              aiSettings?.api_key_set ? 'Key saved — type to replace' : 'Paste the API key'
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
