import { IconDatabase, IconLock, IconCircleCheckFilled } from '@tabler/icons-react';
import { ServiceConfig } from '@/types';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { cn } from '@/utils/cn';
import { dbPasswordError, defaultDbName } from './services';

interface Props {
  data: ServiceConfig;
  onChange: (d: Partial<ServiceConfig>) => void;
  onNext: () => void;
  onBack: () => void;
  origin?: 'scaffold' | 'onboard';
  appName?: string;
}

const PG_SIZES = [
  { value: '1Gi', label: '1 GiB' },
  { value: '5Gi', label: '5 GiB' },
  { value: '20Gi', label: '20 GiB' },
];

function ServiceTile({ icon, label, desc, selected, unavailable, onToggle, children }: {
  icon: JSX.Element;
  label: string;
  desc: string;
  selected: boolean;
  unavailable?: string; // raison affichée en badge quand le service ne peut pas être choisi
  onToggle: () => void;
  children?: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        'border-2 rounded-md transition-colors bg-card',
        unavailable ? 'border-border opacity-60' : selected ? 'border-foreground' : 'border-border'
      )}
    >
      <button
        type="button"
        disabled={!!unavailable}
        className={cn('w-full flex items-center gap-3 p-4 text-left', unavailable ? 'cursor-not-allowed' : 'cursor-pointer')}
        onClick={onToggle}
      >
        <span className="text-muted-foreground">{icon}</span>
        <div className="flex-1">
          <p className="text-sm font-medium text-foreground">{label}</p>
          <p className="text-xs text-muted-foreground">{desc}</p>
        </div>
        {unavailable ? (
          <span className="text-xs font-medium text-muted-foreground bg-muted px-2 py-0.5 rounded-full">{unavailable}</span>
        ) : selected ? (
          <IconCircleCheckFilled size={18} className="text-info" />
        ) : (
          <span className="h-[18px] w-[18px] rounded-full border-2 border-border block" />
        )}
      </button>
      {children}
    </div>
  );
}

export function Step2Services({ data, onChange, onNext, onBack, origin = 'scaffold', appName = '' }: Props) {
  const db = data.database;
  const dbAvailable = origin === 'scaffold';
  const passwordError = db.enabled ? dbPasswordError(db.password) : null;
  const setDb = (patch: Partial<ServiceConfig['database']>) => onChange({ database: { ...db, ...patch } });

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">Select the services to inject into your application.</p>

      <ServiceTile
        icon={<IconDatabase size={18} />}
        label="Database"
        desc={
          dbAvailable
            ? 'PostgreSQL in-cluster, one per environment. Credentials stay in Vault and reach the app as DATABASE_URL.'
            : 'An existing repository keeps its own chart: the CNP cannot add PostgreSQL to it.'
        }
        selected={dbAvailable && db.enabled}
        unavailable={dbAvailable ? undefined : 'New apps only'}
        onToggle={() => setDb({ enabled: !db.enabled })}
      >
        {dbAvailable && db.enabled && (
          <div className="grid gap-3 border-t border-border px-4 py-4 sm:grid-cols-2">
            <Input
              label="Database name"
              mono
              value={db.dbName}
              placeholder={defaultDbName(appName) || 'app_db'}
              onChange={(e) => setDb({ dbName: e.target.value.toLowerCase() })}
              hint="Defaults to the app name"
            />
            <Select
              label="Storage"
              options={PG_SIZES}
              value={db.pgSize}
              onChange={(v) => setDb({ pgSize: v as ServiceConfig['database']['pgSize'] })}
            />
            <div className="sm:col-span-2">
              <Input
                label="Password"
                type="password"
                autoComplete="new-password"
                value={db.password}
                onChange={(e) => setDb({ password: e.target.value })}
                error={passwordError ?? undefined}
                hint={passwordError ? undefined : 'Optional: leave empty to generate a different one for dev and prod. Stored in Vault only.'}
              />
            </div>
          </div>
        )}
      </ServiceTile>

      <ServiceTile
        icon={<IconLock size={18} />}
        label="Authentication"
        desc="Keycloak — dedicated realm per env, delegated admin console"
        selected={data.auth.enabled}
        onToggle={() => onChange({ auth: { enabled: !data.auth.enabled } })}
      />

      <div className="flex justify-between mt-2">
        <Button variant="ghost" size="sm" onClick={onBack}>
          Back
        </Button>
        <Button variant="primary" size="sm" onClick={onNext} disabled={!!passwordError}>
          Next
        </Button>
      </div>
    </div>
  );
}
