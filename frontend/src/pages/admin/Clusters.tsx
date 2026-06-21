import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { clustersApi, ClusterConnection } from '@/api/clusters';

export const Clusters = () => {
  const queryClient = useQueryClient();
  const [isAdding, setIsAdding] = useState(false);
  const [editingCluster, setEditingCluster] = useState<ClusterConnection | null>(null);

  // Form states
  const [name, setName] = useState('');
  const [endpoint, setEndpoint] = useState('');
  const [kubeconfig, setKubeconfig] = useState('');
  const [formError, setFormError] = useState('');

  const { data: clusters = [], isLoading, error: fetchError } = useQuery({
    queryKey: ['admin-clusters'],
    queryFn: () => clustersApi.list(),
  });

  const createMutation = useMutation({
    mutationFn: () => clustersApi.create({ name: name.trim(), endpoint: endpoint.trim(), kubeconfig: kubeconfig.trim() }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-clusters'] });
      resetForm();
    },
    onError: (err: unknown) => {
      const error = err as { response?: { data?: { detail?: string } }; message?: string };
      setFormError(error.response?.data?.detail || error.message || "Erreur lors de la création du cluster.");
    }
  });

  const updateMutation = useMutation({
    mutationFn: (id: number) => {
      const payload: { name?: string; endpoint?: string; kubeconfig?: string } = {};
      if (name.trim()) payload.name = name.trim();
      if (endpoint.trim()) payload.endpoint = endpoint.trim();
      if (kubeconfig.trim()) payload.kubeconfig = kubeconfig.trim();
      return clustersApi.update(id, payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-clusters'] });
      resetForm();
    },
    onError: (err: unknown) => {
      const error = err as { response?: { data?: { detail?: string } }; message?: string };
      setFormError(error.response?.data?.detail || error.message || "Erreur lors de la mise à jour du cluster.");
    }
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => clustersApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-clusters'] });
    },
    onError: (err: unknown) => {
      const error = err as { response?: { data?: { detail?: string } }; message?: string };
      alert(error.response?.data?.detail || error.message || "Impossible de supprimer le cluster.");
    }
  });

  const resetForm = () => {
    setIsAdding(false);
    setEditingCluster(null);
    setName('');
    setEndpoint('');
    setKubeconfig('');
    setFormError('');
  };

  const handleStartAdd = () => {
    resetForm();
    setIsAdding(true);
  };

  const handleStartEdit = (cluster: ClusterConnection) => {
    resetForm();
    setEditingCluster(cluster);
    setName(cluster.name);
    setEndpoint(cluster.endpoint);
    setKubeconfig(''); // blank because it's a password-like secret in Vault
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');

    if (!name.trim()) {
      setFormError("Le nom du cluster est requis.");
      return;
    }
    if (!endpoint.trim()) {
      setFormError("L'endpoint Kubernetes est requis.");
      return;
    }

    if (isAdding) {
      if (!kubeconfig.trim()) {
        setFormError("Le contenu du Kubeconfig est requis pour la création.");
        return;
      }
      createMutation.mutate();
    } else if (editingCluster) {
      updateMutation.mutate(editingCluster.id);
    }
  };

  const handleDelete = (cluster: ClusterConnection) => {
    if (confirm(`Êtes-vous sûr de vouloir supprimer le cluster "${cluster.name}" ?\nCette opération est irréversible et supprimera le kubeconfig associé dans Vault.`)) {
      deleteMutation.mutate(cluster.id);
    }
  };

  const isPending = createMutation.isPending || updateMutation.isPending;

  return (
    <>
      <div className="topbar">
        <span className="topbar-title">Gestion des clusters</span>
      </div>
      <div className="page-content">
        {/* -- Form Section -- */}
        {(isAdding || editingCluster) && (
          <div className="card" style={{ marginBottom: 20 }}>
            <div className="card-header">
              {isAdding ? 'Ajouter un nouveau cluster' : `Modifier le cluster: ${editingCluster?.name}`}
            </div>
            <div style={{ padding: '16px' }}>
              <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {formError && (
                  <div className="alert error">
                    <i className="ti ti-alert-circle" aria-hidden="true" />
                    {formError}
                  </div>
                )}
                
                <div className="form-group">
                  <label className="form-label">Nom du cluster</label>
                  <input
                    type="text"
                    className="form-input"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    placeholder="ex: prod-cluster-1"
                    disabled={isPending}
                    required
                  />
                  <span className="form-hint">Un identifiant unique pour ce cluster (ex: prod-k8s, staging-gcp)</span>
                </div>

                <div className="form-group">
                  <label className="form-label">Endpoint API Kubernetes</label>
                  <input
                    type="url"
                    className="form-input mono"
                    value={endpoint}
                    onChange={e => setEndpoint(e.target.value)}
                    placeholder="https://10.0.0.1:6443"
                    disabled={isPending}
                    required
                  />
                  <span className="form-hint">L'URL du serveur API de Kubernetes (doit être accessible par le backend)</span>
                </div>

                <div className="form-group">
                  <label className="form-label">
                    Kubeconfig (YAML) {editingCluster && <span style={{ fontWeight: 'normal', color: 'var(--text-muted)' }}>(Laisser vide pour ne pas modifier)</span>}
                  </label>
                  <textarea
                    className="form-textarea mono"
                    rows={8}
                    value={kubeconfig}
                    onChange={e => setKubeconfig(e.target.value)}
                    placeholder={editingCluster ? "••••••••••••••••••••" : "apiVersion: v1\nkind: Config\n..."}
                    disabled={isPending}
                    required={isAdding}
                  />
                  <span className="form-hint">
                    Le contenu complet du fichier kubeconfig au format YAML. Il sera stocké de manière sécurisée dans HashiCorp Vault.
                  </span>
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 4 }}>
                  <button type="button" className="btn btn-ghost btn-sm" onClick={resetForm} disabled={isPending}>
                    Annuler
                  </button>
                  <button type="submit" className="btn btn-primary btn-sm" disabled={isPending}>
                    <i className="ti ti-device-floppy" aria-hidden="true" />
                    {isPending ? 'Sauvegarde en cours…' : 'Sauvegarder'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* -- Main Table -- */}
        {isLoading ? (
          <div className="loading-state">
            <i className="ti ti-loader-2" aria-hidden="true" style={{ fontSize: 16 }} />
            Chargement des clusters…
          </div>
        ) : fetchError ? (
          <div className="alert error">
            <i className="ti ti-alert-circle" aria-hidden="true" />
            Erreur lors de la récupération des clusters : {fetchError instanceof Error ? fetchError.message : String(fetchError)}
          </div>
        ) : (
          <div className="card">
            <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>Clusters enregistrés ({clusters.length})</span>
              {!isAdding && !editingCluster && (
                <button className="btn btn-primary btn-sm" onClick={handleStartAdd}>
                  <i className="ti ti-plus" aria-hidden="true" /> Ajouter un cluster
                </button>
              )}
            </div>
            
            <table className="data-table">
              <thead>
                <tr>
                  <th>Nom</th>
                  <th>Endpoint API</th>
                  <th>Vault Secret Path</th>
                  <th>Date d'ajout</th>
                  <th style={{ width: 100, textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {clusters.map((cluster) => (
                  <tr key={cluster.id}>
                    <td style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <i className="ti ti-server" style={{ color: 'var(--accent)' }} aria-hidden="true" />
                        {cluster.name}
                      </div>
                    </td>
                    <td className="mono" style={{ fontSize: '11px' }}>{cluster.endpoint}</td>
                    <td className="mono" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                      {cluster.kubeconfig_secret_ref}
                    </td>
                    <td style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                      {new Date(cluster.created_at).toLocaleDateString('fr-FR', {
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </td>
                    <td>
                      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                        <button
                          className="btn-icon"
                          style={{ width: 28, height: 28 }}
                          onClick={() => handleStartEdit(cluster)}
                          title="Modifier"
                        >
                          <i className="ti ti-edit" style={{ fontSize: 14 }} aria-hidden="true" />
                        </button>
                        <button
                          className="btn-icon"
                          style={{ width: 28, height: 28 }}
                          onClick={() => handleDelete(cluster)}
                          title="Supprimer"
                        >
                          <i className="ti ti-trash" style={{ fontSize: 14, color: 'var(--red)' }} aria-hidden="true" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {clusters.length === 0 && (
                  <tr>
                    <td colSpan={5} style={{ textAlign: 'center', padding: '32px 16px', color: 'var(--text-muted)' }}>
                      Aucun cluster enregistré. Cliquez sur "Ajouter un cluster" pour commencer.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
};
