import {
  IconDatabase,
  IconLock,
  IconBolt,
  IconCircleCheckFilled,
} from '@tabler/icons-react';
import { ServiceConfig } from '@/types';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { cn } from '@/utils/cn';

interface Props {
  data: ServiceConfig;
  onChange: (d: Partial<ServiceConfig>) => void;
  onNext: () => void;
  onBack: () => void;
}

const SERVICES = [
  {
    key: 'database' as const,
    icon: <IconDatabase size={18} />,
    label: 'Database',
    desc: 'PostgreSQL managed in-cluster',
    soon: false,
  },
  {
    key: 'auth' as const,
    icon: <IconLock size={18} />,
    label: 'Authentication',
    desc: 'Keycloak — SSO & account management',
    soon: true,
  },
  {
    key: 'cache' as const,
    icon: <IconBolt size={18} />,
    label: 'Cache',
    desc: 'Redis — memory cache',
    soon: true,
  },
];

export function Step2Services({ data, onChange, onNext, onBack }: Props) {
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        Select the services to inject into your application.
      </p>

      {SERVICES.map((svc) => {
        const enabled =
          svc.key === 'database'
            ? data.database.enabled
            : svc.key === 'auth'
            ? data.auth.enabled
            : data.cache.enabled;

        return (
          <div
            key={svc.key}
            className={cn(
              'border-2 rounded-md transition-colors bg-card',
              svc.soon
                ? 'border-border opacity-60'
                : enabled
                ? 'border-foreground'
                : 'border-border'
            )}
          >
            <button
              type="button"
              disabled={svc.soon}
              className={cn(
                'w-full flex items-center gap-3 p-4 text-left',
                svc.soon ? 'cursor-not-allowed' : 'cursor-pointer'
              )}
              onClick={() => {
                if (svc.soon) return;
                if (svc.key === 'database') {
                  onChange({ database: { ...data.database, enabled: !data.database.enabled } });
                } else if (svc.key === 'auth') {
                  onChange({ auth: { enabled: !data.auth.enabled } });
                } else {
                  onChange({ cache: { enabled: !data.cache.enabled } });
                }
              }}
            >
              <span className="text-muted-foreground">{svc.icon}</span>
              <div className="flex-1">
                <p className="text-sm font-medium text-foreground">{svc.label}</p>
                <p className="text-xs text-muted-foreground">{svc.desc}</p>
              </div>
              {svc.soon ? (
                <span className="text-xs font-medium text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
                  Soon
                </span>
              ) : enabled ? (
                <IconCircleCheckFilled size={18} className="text-info" />
              ) : (
                <span className="h-[18px] w-[18px] rounded-full border-2 border-border block" />
              )}
            </button>

            {svc.key === 'database' && data.database.enabled && (
              <div className="px-4 pb-4 pt-0 bg-background-subtle rounded-b-md flex gap-3">
                <Select
                  label="Type"
                  options={[{ value: 'postgresql', label: 'PostgreSQL' }]}
                  value="postgresql"
                  onChange={() => {}}
                  className="w-36"
                />
                <Input
                  label="DB name"
                  value={data.database.dbName}
                  onChange={(e) =>
                    onChange({
                      database: { ...data.database, dbName: e.target.value },
                    })
                  }
                  placeholder="myapp_db"
                  className="flex-1"
                />
                <Select
                  label="Size"
                  options={[
                    { value: '1Gi', label: '1 Gi' },
                    { value: '5Gi', label: '5 Gi' },
                    { value: '20Gi', label: '20 Gi' },
                  ]}
                  value={data.database.pgSize}
                  onChange={(v) =>
                    onChange({
                      database: {
                        ...data.database,
                        pgSize: v as '1Gi' | '5Gi' | '20Gi',
                      },
                    })
                  }
                  className="w-24"
                />
              </div>
            )}
          </div>
        );
      })}

      <div className="flex justify-between mt-2">
        <Button variant="ghost" size="sm" onClick={onBack}>
          Back
        </Button>
        <Button variant="primary" size="sm" onClick={onNext}>
          Next
        </Button>
      </div>
    </div>
  );
}
