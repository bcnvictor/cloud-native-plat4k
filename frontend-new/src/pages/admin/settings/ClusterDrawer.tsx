import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { IconPlugConnected, IconX } from '@tabler/icons-react';
import { clustersApi } from '@/api/clusters';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { toast } from '@/components/ui/toast';
import { apiError } from '@/utils/apiError';
import { PROVIDER_LABELS } from '@/utils/clusterUtils';
import type { ClusterConnection, ClusterConnectionPayload, ClusterProvider, ClusterTestResult } from '@/types';
import { TestResultLine } from './TestResultLine';

interface ClusterDrawerProps {
  // null = création d'un nouveau cluster
  cluster: ClusterConnection | null;
  onClose: () => void;
}

const URL_FIELDS = ['prometheus_url', 'loki_url', 'argocd_url'] as const;

const PROVIDER_OPTIONS = (Object.keys(PROVIDER_LABELS) as ClusterProvider[]).map((value) => ({
  value,
  label: PROVIDER_LABELS[value],
}));

export function ClusterDrawer({ cluster, onClose }: ClusterDrawerProps) {
  const qc = useQueryClient();
  const editing = cluster !== null;

  const [name, setName] = useState(cluster?.name ?? '');
  const [endpoint, setEndpoint] = useState(cluster?.endpoint ?? '');
  // Pas de valeur par défaut à la création : l'admin doit choisir le cloud explicitement.
  const [provider, setProvider] = useState<ClusterProvider | ''>(cluster?.provider ?? '');
  const [urls, setUrls] = useState<Record<(typeof URL_FIELDS)[number], string>>({
    prometheus_url: cluster?.prometheus_url ?? '',
    loki_url: cluster?.loki_url ?? '',
    argocd_url: cluster?.argocd_url ?? '',
  });
  const [replaceKubeconfig, setReplaceKubeconfig] = useState(!editing);
  const [kubeconfig, setKubeconfig] = useState('');
  const [argocdToken, setArgocdToken] = useState('');
  const [testResult, setTestResult] = useState<ClusterTestResult | null>(null);

  function buildPayload(): ClusterConnectionPayload {
    if (!editing) {
      return {
        name: name.trim(),
        endpoint: endpoint.trim(),
        ...(provider ? { provider } : {}),
        kubeconfig,
        ...Object.fromEntries(URL_FIELDS.map((f) => [f, urls[f].trim() || null])),
        ...(argocdToken ? { argocd_token: argocdToken } : {}),
      };
    }
    // En édition, on n'envoie que les champs modifiés : l'audit log liste ce qui a changé.
    const payload: ClusterConnectionPayload = {};
    if (name.trim() !== cluster.name) payload.name = name.trim();
    if (endpoint.trim() !== cluster.endpoint) payload.endpoint = endpoint.trim();
    if (provider && provider !== cluster.provider) payload.provider = provider;
    for (const f of URL_FIELDS) {
      const value = urls[f].trim() || null;
      if (value !== (cluster[f] ?? null)) payload[f] = value;
    }
    if (replaceKubeconfig && kubeconfig) payload.kubeconfig = kubeconfig;
    if (argocdToken) payload.argocd_token = argocdToken;
    return payload;
  }

  const save = useMutation({
    mutationFn: () => {
      const payload = buildPayload();
      return editing ? clustersApi.update(cluster.id, payload) : clustersApi.register(payload);
    },
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ['clusters'] });
      qc.invalidateQueries({ queryKey: ['audit-logs'] });
      toast({ title: editing ? `${saved.name} updated` : `${saved.name} added` });
      onClose();
    },
  });

  const test = useMutation({
    mutationFn: () =>
      kubeconfig ? clustersApi.testKubeconfig(kubeconfig) : clustersApi.test(cluster!.id),
    onMutate: () => setTestResult(null),
    onSuccess: setTestResult,
    onError: (err) => setTestResult({ reachable: false, latency_ms: null, namespace_count: null, error: apiError(err) }),
  });

  const unchanged = editing && Object.keys(buildPayload()).length === 0;
  const canSave = name.trim() && endpoint.trim() && provider && (editing || kubeconfig) && !unchanged;
  const canTest = Boolean(kubeconfig) || editing;

  return (
    <>
      <div className="fixed inset-0 z-[60] bg-black/30" onClick={onClose} />
      <aside
        role="dialog"
        aria-label={editing ? `Edit ${cluster.name}` : 'Add cluster'}
        className="fixed inset-y-0 right-0 z-[60] w-full max-w-md bg-background border-l border-border flex flex-col"
      >
        <header className="flex items-center justify-between px-5 py-3.5 border-b border-border">
          <h2 className="text-sm font-semibold text-foreground">
            {editing ? `Edit ${cluster.name}` : 'Add cluster'}
          </h2>
          <button onClick={onClose} aria-label="Close" className="text-muted-foreground hover:text-foreground">
            <IconX size={16} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-5 flex flex-col gap-4">
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Connection</p>
          <Input id="cluster-name" label="Name" mono value={name} onChange={(e) => setName(e.target.value)} placeholder="cnp-prod" />
          <Input id="cluster-endpoint" label="API endpoint" mono value={endpoint} onChange={(e) => setEndpoint(e.target.value)} placeholder="https://k8s.example.com:6443" />
          <Select
            label="Cloud provider"
            options={PROVIDER_OPTIONS}
            value={provider}
            onChange={(v) => setProvider(v as ClusterProvider)}
            placeholder="Select a provider…"
          />

          <div className="flex flex-col gap-1">
            <label htmlFor="cluster-kubeconfig" className="text-sm font-medium text-foreground">Kubeconfig</label>
            {editing && !replaceKubeconfig ? (
              <div className="flex items-center justify-between gap-2 px-3 py-2 border border-dashed border-border rounded-md">
                <span className="text-xs font-mono text-muted-foreground truncate">{cluster.kubeconfig_secret_ref}</span>
                <Button size="sm" onClick={() => setReplaceKubeconfig(true)}>Replace</Button>
              </div>
            ) : (
              <>
                <textarea
                  id="cluster-kubeconfig"
                  value={kubeconfig}
                  onChange={(e) => setKubeconfig(e.target.value)}
                  rows={6}
                  placeholder="Paste kubeconfig content…"
                  className="w-full px-3 py-2 text-xs font-mono rounded-md border border-input bg-background resize-y focus:outline-none focus:ring-2 focus:ring-ring"
                />
                <p className="text-xs text-muted-foreground">Stored encrypted in Vault and never displayed again.</p>
              </>
            )}
          </div>

          <p className="text-[11px] uppercase tracking-wide text-muted-foreground pt-1">Observability</p>
          <Input id="cluster-prometheus" label="Prometheus URL" mono value={urls.prometheus_url} onChange={(e) => setUrls({ ...urls, prometheus_url: e.target.value })} placeholder="https://prometheus…" />
          <Input id="cluster-loki" label="Loki URL" mono value={urls.loki_url} onChange={(e) => setUrls({ ...urls, loki_url: e.target.value })} placeholder="https://loki…" />

          <p className="text-[11px] uppercase tracking-wide text-muted-foreground pt-1">GitOps</p>
          <Input id="cluster-argocd" label="ArgoCD URL" mono value={urls.argocd_url} onChange={(e) => setUrls({ ...urls, argocd_url: e.target.value })} placeholder="https://argocd…" />
          <Input
            id="cluster-argocd-token"
            label="ArgoCD token"
            type="password"
            mono
            value={argocdToken}
            onChange={(e) => setArgocdToken(e.target.value)}
            placeholder={editing ? 'Leave empty to keep the current token' : 'Optional'}
          />

          <p className="text-xs text-primary bg-primary-subtle border border-primary-border rounded-md px-3 py-2">
            Saving is recorded in the audit log ({editing ? 'cluster.updated' : 'cluster.created'}) with the
            names of the changed fields, never their secret values.
          </p>
        </div>

        <footer className="px-5 py-3 border-t border-border flex flex-col gap-2">
          {testResult && <TestResultLine result={testResult} />}
          {save.isError && <p className="text-xs text-danger-text">Save failed · {apiError(save.error)}</p>}
          <div className="flex items-center justify-between gap-2">
            <Button size="sm" icon={<IconPlugConnected size={13} />} loading={test.isPending} disabled={!canTest} onClick={() => test.mutate()}>
              Test connection
            </Button>
            <div className="flex gap-2">
              <Button size="sm" variant="ghost" onClick={onClose}>Cancel</Button>
              <Button size="sm" variant="primary" loading={save.isPending} disabled={!canSave} onClick={() => save.mutate()}>
                {editing ? 'Save changes' : 'Add cluster'}
              </Button>
            </div>
          </div>
        </footer>
      </aside>
    </>
  );
}
