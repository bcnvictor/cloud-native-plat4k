import { IconChevronDown, IconChevronUp, IconCloud, IconPlus, IconServer, IconTrash } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { CiDeployConfig } from '@/types';
import { clustersApi } from '@/api/clusters';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { cn } from '@/utils/cn';

interface Props {
  data: CiDeployConfig;
  onChange: (d: Partial<CiDeployConfig>) => void;
  onNext: () => void;
  onBack: () => void;
}

const TRIGGERS: Array<{ value: 'on_commit' | 'on_tag'; label: string; desc: string }> = [
  { value: 'on_commit', label: 'On every commit', desc: 'Deploys automatically on main.' },
  { value: 'on_tag', label: 'On tag', desc: 'Deploys only on Git tags.' },
];

export function Step3CiDeploy({ data, onChange, onNext, onBack }: Props) {
  const { data: clusters = [] } = useQuery({
    queryKey: ['clusters'],
    queryFn: clustersApi.list,
  });

  return (
    <div className="flex flex-col gap-5">
      {/* Target cloud */}
      <div className="flex flex-col gap-3">
        <p className="text-sm font-medium text-foreground">Target cloud</p>
        {clusters.length === 0 ? (
          <p className="text-xs text-muted-foreground px-1">No clusters registered — default will be used.</p>
        ) : (
          clusters.map((c) => {
            const selected = data.targetClusterId === c.id;
            const isPrivate = !c.endpoint.includes('azure') && !c.endpoint.includes('aks');
            return (
              <button
                key={c.id}
                onClick={() => onChange({ targetClusterId: c.id })}
                className={cn(
                  'flex items-center gap-3 p-4 rounded-md border-2 text-left transition-colors bg-card',
                  selected ? 'border-foreground' : 'border-border hover:border-muted-foreground'
                )}
              >
                <span
                  className={cn(
                    'h-4 w-4 rounded-full border-2 shrink-0 flex items-center justify-center',
                    selected ? 'border-info' : 'border-muted-foreground'
                  )}
                >
                  {selected && <span className="h-2 w-2 rounded-full bg-info block" />}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground">{c.name}</p>
                  <p className="text-xs text-muted-foreground truncate">{c.endpoint}</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {isPrivate ? (
                    <IconServer size={13} className="text-muted-foreground" />
                  ) : (
                    <IconCloud size={13} className="text-muted-foreground" />
                  )}
                  <span className={cn(
                    'text-xs px-2 py-0.5 rounded-full',
                    c.status === 'online' ? 'bg-success/15 text-success-text' : 'bg-muted text-muted-foreground'
                  )}>
                    {c.status}
                  </span>
                </div>
              </button>
            );
          })
        )}
      </div>

      {/* Deploy trigger */}
      <div className="flex flex-col gap-3">
        <p className="text-sm font-medium text-foreground">Deploy trigger</p>
        {TRIGGERS.map((t) => {
          const selected = data.trigger === t.value;
          return (
            <button
              key={t.value}
              onClick={() => onChange({ trigger: t.value })}
              className={cn(
                'flex items-center gap-3 p-4 rounded-md border-2 text-left transition-colors bg-card',
                selected ? 'border-foreground' : 'border-border hover:border-muted-foreground'
              )}
            >
              <span
                className={cn(
                  'h-4 w-4 rounded-full border-2 shrink-0 flex items-center justify-center',
                  selected ? 'border-info' : 'border-muted-foreground'
                )}
              >
                {selected && (
                  <span className="h-2 w-2 rounded-full bg-info block" />
                )}
              </span>
              <div>
                <p className="text-sm font-medium text-foreground">{t.label}</p>
                <p className="text-xs text-muted-foreground">{t.desc}</p>
              </div>
            </button>
          );
        })}
      </div>

      {/* Advanced options */}
      <div className="border border-border rounded-md overflow-hidden">
        <button
          className="w-full flex items-center justify-between px-4 py-3 hover:bg-accent transition-colors text-sm"
          onClick={() => onChange({ advancedOpen: !data.advancedOpen })}
        >
          <span className="font-medium text-foreground">Advanced options</span>
          {data.advancedOpen ? (
            <IconChevronUp size={14} className="text-muted-foreground" />
          ) : (
            <IconChevronDown size={14} className="text-muted-foreground" />
          )}
        </button>

        {data.advancedOpen && (
          <div className="px-4 pb-4 border-t border-border bg-background-subtle flex flex-col gap-4 pt-4">
            {/* Env vars */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs font-medium text-foreground">Environment variables</p>
                <Button
                  variant="ghost"
                  size="sm"
                  icon={<IconPlus size={12} />}
                  onClick={() =>
                    onChange({
                      envVars: [...data.envVars, { key: '', value: '', masked: false }],
                    })
                  }
                >
                  Add
                </Button>
              </div>
              {data.envVars.map((ev, i) => (
                <div key={i} className="flex gap-2 mb-2">
                  <Input
                    placeholder="KEY"
                    value={ev.key}
                    mono
                    onChange={(e) => {
                      const next = [...data.envVars];
                      next[i] = { ...next[i], key: e.target.value };
                      onChange({ envVars: next });
                    }}
                    className="flex-1"
                  />
                  <Input
                    placeholder="value"
                    value={ev.value}
                    mono
                    onChange={(e) => {
                      const next = [...data.envVars];
                      next[i] = { ...next[i], value: e.target.value };
                      onChange({ envVars: next });
                    }}
                    className="flex-1"
                  />
                  <button
                    onClick={() => {
                      onChange({ envVars: data.envVars.filter((_, j) => j !== i) });
                    }}
                    className="text-muted-foreground hover:text-danger"
                  >
                    <IconTrash size={14} />
                  </button>
                </div>
              ))}
            </div>

            {/* Replicas */}
            <Input
              label="Replica count"
              type="number"
              value={data.replicas}
              onChange={(e) => onChange({ replicas: parseInt(e.target.value) || 1 })}
              className="w-24"
            />

            <p className="text-xs text-muted-foreground">
              Everything can be reconfigured after creation from the app settings.
            </p>
          </div>
        )}
      </div>

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
