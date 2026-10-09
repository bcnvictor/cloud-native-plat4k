import type { KeycloakInstanceSummary } from '@/types';

export function AuthInstanceInfo({ instance }: { instance: KeycloakInstanceSummary | null }) {
  if (!instance) return <p className="text-xs text-muted-foreground mb-3">No Keycloak instance configured.</p>;
  return (
    <div className="text-xs text-muted-foreground mb-3 space-y-1">
      <p>{instance.source === 'legacy' ? 'Legacy configuration' : <>Instance: <span className="font-medium text-foreground">{instance.instance_key}</span> · {instance.cluster_name ?? 'Cluster connection removed'}</>}</p>
      <a className="block break-all text-primary hover:underline" href={instance.public_url} target="_blank" rel="noopener noreferrer">{instance.public_url}</a>
      {!instance.enabled && <p className="text-warning-text">Instance unavailable. Contact a platform administrator.</p>}
    </div>
  );
}
