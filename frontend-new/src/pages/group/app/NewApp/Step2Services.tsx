import {
  IconDatabase,
  IconLock,
  IconBolt,
  IconCircleCheckFilled,
} from '@tabler/icons-react';
import { ServiceConfig } from '@/types';
import { Button } from '@/components/ui/Button';
import { cn } from '@/utils/cn';

interface Props {
  data: ServiceConfig;
  onChange: (d: Partial<ServiceConfig>) => void;
  onNext: () => void;
  onBack: () => void;
}

// `badge`: why a service can't be picked in the wizard (null = selectable).
const SERVICES: {
  key: 'database' | 'auth' | 'cache';
  icon: JSX.Element;
  label: string;
  desc: string;
  badge: 'CLI/API' | 'Soon' | null;
}[] = [
  {
    key: 'database',
    icon: <IconDatabase size={18} />,
    label: 'Database',
    // Not sent by the wizard (see services.ts): scaffold-time PostgreSQL stays CLI/API only.
    desc: 'PostgreSQL managed in-cluster — available through the CLI/API only',
    badge: 'CLI/API',
  },
  {
    key: 'auth',
    icon: <IconLock size={18} />,
    label: 'Authentication',
    desc: 'Keycloak — dedicated realm per env, delegated admin console',
    badge: null,
  },
  {
    key: 'cache',
    icon: <IconBolt size={18} />,
    label: 'Cache',
    desc: 'Redis — memory cache',
    badge: 'Soon',
  },
];

export function Step2Services({ data, onChange, onNext, onBack }: Props) {
  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        Select the services to inject into your application.
      </p>

      {SERVICES.map((svc) => {
        const unavailable = svc.badge !== null;
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
              unavailable
                ? 'border-border opacity-60'
                : enabled
                ? 'border-foreground'
                : 'border-border'
            )}
          >
            <button
              type="button"
              disabled={unavailable}
              className={cn(
                'w-full flex items-center gap-3 p-4 text-left',
                unavailable ? 'cursor-not-allowed' : 'cursor-pointer'
              )}
              onClick={() => {
                if (unavailable) return;
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
              {unavailable ? (
                <span className="text-xs font-medium text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
                  {svc.badge}
                </span>
              ) : enabled ? (
                <IconCircleCheckFilled size={18} className="text-info" />
              ) : (
                <span className="h-[18px] w-[18px] rounded-full border-2 border-border block" />
              )}
            </button>
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
