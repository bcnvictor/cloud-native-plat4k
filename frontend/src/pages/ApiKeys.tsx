import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { authApi } from '@/api/auth';
import { SettingsLayout } from '@/components/SettingsLayout';

export const ApiKeys = () => {
  const queryClient = useQueryClient();
  const [label, setLabel] = useState('');
  const [newKey, setNewKey] = useState<{ raw: string; label: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [revokingId, setRevokingId] = useState<number | null>(null);

  const { data: keys, isLoading } = useQuery({
    queryKey: ['apikeys'],
    queryFn: () => authApi.getApiKeys(),
  });

  const createMutation = useMutation({
    mutationFn: (lbl: string) => authApi.createApiKey(lbl),
    onSuccess: (data) => {
      setNewKey({ raw: data.api_key, label: data.label });
      setLabel('');
      queryClient.invalidateQueries({ queryKey: ['apikeys'] });
    },
  });

  const revokeMutation = useMutation({
    mutationFn: (id: number) => authApi.revokeApiKey(id),
    onSuccess: () => {
      setRevokingId(null);
      queryClient.invalidateQueries({ queryKey: ['apikeys'] });
    },
    onError: () => setRevokingId(null),
  });

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (label.trim()) createMutation.mutate(label.trim());
  };

  const copyKey = () => {
    if (!newKey) return;
    navigator.clipboard.writeText(newKey.raw);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const activeKeys = keys?.filter(k => !k.revoked) ?? [];

  return (
    <SettingsLayout
      title="Token d'accès"
      description="Clés API utilisées par le CLI CNP. Ne pas partager."
    >
      {/* Create form */}
      <div className="card">
        <div className="card-header">Générer une clé</div>
        <div style={{ padding: '16px' }}>
          <form onSubmit={handleCreate}>
            <div className="form-row">
              <div className="form-group" style={{ flex: 1 }}>
                <label className="form-label" htmlFor="key-label">Label de la clé</label>
                <input
                  id="key-label"
                  type="text"
                  className="form-input"
                  placeholder="ex. Mon MacBook CLI"
                  value={label}
                  onChange={e => setLabel(e.target.value)}
                />
              </div>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={!label.trim() || createMutation.isPending}
                style={{ flexShrink: 0 }}
              >
                <i className="ti ti-plus" aria-hidden="true" />
                {createMutation.isPending ? 'Génération…' : 'Générer'}
              </button>
            </div>
          </form>
        </div>

        {newKey && (
          <div style={{ padding: '0 16px 16px' }}>
            <div className="new-key-reveal">
              <div className="new-key-title">
                <i className="ti ti-alert-triangle" style={{ marginRight: 6 }} aria-hidden="true" />
                Copiez cette clé maintenant !
              </div>
              <div className="new-key-sub">
                Elle ne sera plus affichée après fermeture. Label : <strong>{newKey.label}</strong>
              </div>
              <div className="new-key-row">
                <div className="new-key-code">{newKey.raw}</div>
                <button className="btn btn-ghost btn-sm" onClick={copyKey}>
                  <i className={`ti ${copied ? 'ti-check' : 'ti-copy'}`} aria-hidden="true" />
                  {copied ? 'Copié !' : 'Copier'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Keys list */}
      <div className="card">
        <div className="card-header">Clés actives</div>

        {isLoading ? (
          <div className="loading-state" style={{ padding: 24 }}>Chargement…</div>
        ) : activeKeys.length === 0 ? (
          <div style={{ padding: '24px 16px', fontSize: 12, color: 'var(--text-muted)', textAlign: 'center' }}>
            Aucune clé API active.
          </div>
        ) : (
          activeKeys.map(key => (
            <div key={key.id} className="token-row">
              <div>
                <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 2 }}>
                  {key.label}
                </div>
                <div style={{ fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--text-muted)' }}>
                  Créé le {new Date(key.created_at).toLocaleDateString('fr-FR')}
                  {key.last_used_at && (
                    <> · Dernière utilisation : {new Date(key.last_used_at).toLocaleDateString('fr-FR')}</>
                  )}
                </div>
              </div>
              <div className="token-actions">
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => { setRevokingId(key.id); revokeMutation.mutate(key.id); }}
                  disabled={revokingId === key.id}
                  style={{ color: 'var(--red)', borderColor: 'rgba(239,68,68,0.25)' }}
                >
                  <i className="ti ti-trash" aria-hidden="true" />Révoquer
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </SettingsLayout>
  );
};
