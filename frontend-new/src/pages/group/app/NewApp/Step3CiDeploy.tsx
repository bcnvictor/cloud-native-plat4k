import { IconChevronDown, IconChevronUp, IconPlus, IconTrash } from '@tabler/icons-react';
import { CiDeployConfig } from '@/types';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { cn } from '@/lib/cn';

interface Props {
  data: CiDeployConfig;
  onChange: (d: Partial<CiDeployConfig>) => void;
  onNext: () => void;
  onBack: () => void;
}

const TRIGGERS: Array<{ value: 'on_commit' | 'on_tag'; label: string; desc: string }> = [
  { value: 'on_commit', label: 'Sur chaque commit', desc: 'Déploie automatiquement sur main.' },
  { value: 'on_tag', label: 'Sur tag', desc: 'Déploie uniquement sur les tags Git.' },
];

export function Step3CiDeploy({ data, onChange, onNext, onBack }: Props) {
  return (
    <div className="flex flex-col gap-5">
      {/* Trigger selection */}
      <div className="flex flex-col gap-3">
        <p className="text-sm font-medium text-foreground">Déclencheur de déploiement</p>
        {TRIGGERS.map((t) => {
          const selected = data.trigger === t.value;
          return (
            <button
              key={t.value}
              onClick={() => onChange({ trigger: t.value })}
              className={cn(
                'flex items-center gap-3 p-4 rounded-md border-2 text-left transition-colors',
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
          <span className="font-medium text-foreground">Options avancées</span>
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
                <p className="text-xs font-medium text-foreground">Variables d'environnement</p>
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
                  Ajouter
                </Button>
              </div>
              {data.envVars.map((ev, i) => (
                <div key={i} className="flex gap-2 mb-2">
                  <Input
                    placeholder="CLE"
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
                    placeholder="valeur"
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
              label="Nombre de replicas"
              type="number"
              value={data.replicas}
              onChange={(e) => onChange({ replicas: parseInt(e.target.value) || 1 })}
              className="w-24"
            />

            <p className="text-xs text-muted-foreground">
              Tout est configurable après création depuis les settings de l'application.
            </p>
          </div>
        )}
      </div>

      <div className="flex justify-between mt-2">
        <Button variant="ghost" size="sm" onClick={onBack}>
          Précédent
        </Button>
        <Button variant="primary" size="sm" onClick={onNext}>
          Suivant
        </Button>
      </div>
    </div>
  );
}
