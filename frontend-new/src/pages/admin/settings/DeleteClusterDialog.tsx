import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { clustersApi } from '@/api/clusters';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { toast } from '@/components/ui/toast';
import { apiError } from '@/utils/apiError';
import type { ClusterConnection } from '@/types';

interface DeleteClusterDialogProps {
  cluster: ClusterConnection;
  onClose: () => void;
}

export function DeleteClusterDialog({ cluster, onClose }: DeleteClusterDialogProps) {
  const qc = useQueryClient();
  const [confirmation, setConfirmation] = useState('');
  const blocked = cluster.app_count > 0;

  const remove = useMutation({
    mutationFn: () => clustersApi.remove(cluster.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['clusters'] });
      qc.invalidateQueries({ queryKey: ['audit-logs'] });
      toast({ title: `${cluster.name} deleted` });
      onClose();
    },
  });

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div role="alertdialog" aria-label={`Delete ${cluster.name}`} className="relative bg-background border border-border rounded-lg shadow-lg p-6 w-full max-w-md mx-4 flex flex-col gap-4">
        <h3 className="text-sm font-semibold text-foreground">Delete {cluster.name}?</h3>
        {blocked ? (
          <>
            <p className="text-xs text-danger-text bg-danger-subtle border border-danger-border rounded-md px-3 py-2">
              {cluster.app_count} application{cluster.app_count > 1 ? 's target' : ' targets'} this cluster.
              Move {cluster.app_count > 1 ? 'them' : 'it'} to another cluster before deleting the connection.
            </p>
            <div className="flex justify-end">
              <Button size="sm" onClick={onClose}>Close</Button>
            </div>
          </>
        ) : (
          <>
            <p className="text-sm text-muted-foreground">
              The connection and its kubeconfig in Vault will be deleted. Resources running on the cluster are not touched.
            </p>
            <Input
              id="delete-cluster-confirm"
              label={`Type ${cluster.name} to confirm`}
              mono
              autoComplete="off"
              value={confirmation}
              onChange={(e) => setConfirmation(e.target.value)}
            />
            {remove.isError && <p className="text-xs text-danger-text">Delete failed · {apiError(remove.error)}</p>}
            <div className="flex justify-end gap-2">
              <Button size="sm" variant="ghost" onClick={onClose} disabled={remove.isPending}>Cancel</Button>
              <Button size="sm" variant="danger" loading={remove.isPending} disabled={confirmation !== cluster.name} onClick={() => remove.mutate()}>
                Delete
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
