import { Step1Data, ServiceConfig, CiDeployConfig } from '@/types';
import { Button } from '@/components/ui/Button';
import { computeSlug } from '@/utils/slugify';

interface Props {
  identity: Step1Data;
  services: ServiceConfig;
  ciDeploy: CiDeployConfig;
  onSubmit: () => void;
  onBack: () => void;
  isPending: boolean;
  error: string | null;
}

function RecapSection({
  title,
  rows,
}: {
  title: string;
  rows: Array<{ label: string; value: string; mono?: boolean }>;
}) {
  return (
    <div className="border border-border rounded-md overflow-hidden">
      <div className="px-4 py-2.5 bg-background-subtle border-b border-border">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          {title}
        </p>
      </div>
      <dl className="px-4 py-3 flex flex-col gap-2">
        {rows.map(({ label, value, mono }) => (
          <div key={label} className="flex items-baseline gap-2">
            <dt className="text-xs text-muted-foreground w-32 shrink-0">{label}</dt>
            <dd className={`text-xs text-foreground ${mono ? 'font-mono' : ''}`}>{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function Step4Recap({ identity, services, ciDeploy, onSubmit, onBack, isPending, error }: Props) {
  const enabledServices = [
    services.database.enabled && 'Base de données (PostgreSQL)',
    services.auth.enabled && 'Authentification (Keycloak)',
    services.cache.enabled && 'Cache (Redis)',
  ].filter(Boolean) as string[];

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        Vérifiez les informations avant de créer l'application.
      </p>

      <RecapSection
        title="Identité"
        rows={[
          { label: 'Nom', value: identity.name },
          { label: 'Slug', value: computeSlug(identity.name), mono: true },
          { label: 'Origine', value: identity.origin },
          { label: 'Framework', value: identity.framework || '—' },
        ]}
      />

      <RecapSection
        title="Services"
        rows={
          enabledServices.length > 0
            ? enabledServices.map((s, i) => ({ label: i === 0 ? 'Services' : '', value: s }))
            : [{ label: 'Services', value: 'Aucun' }]
        }
      />

      <RecapSection
        title="CI & Déploiement"
        rows={[
          {
            label: 'Trigger',
            value: ciDeploy.trigger === 'on_commit' ? 'Sur chaque commit' : 'Sur tag',
          },
          { label: 'Replicas', value: String(ciDeploy.replicas) },
          { label: 'Cluster cible', value: ciDeploy.targetClusterId ? `cluster-${ciDeploy.targetClusterId}` : 'Auto' },
        ]}
      />

      {error && <p className="text-xs text-danger-text">{error}</p>}

      <div className="flex justify-between mt-2">
        <Button variant="ghost" size="sm" onClick={onBack} disabled={isPending}>
          Précédent
        </Button>
        <Button variant="primary" size="sm" loading={isPending} onClick={onSubmit}>
          Créer l'application
        </Button>
      </div>
    </div>
  );
}
