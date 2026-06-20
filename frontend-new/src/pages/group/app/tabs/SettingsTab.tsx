import { useState, useEffect } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { IconEye, IconEyeOff, IconPlus, IconTrash } from '@tabler/icons-react';
import { useAppDetail } from '@/layouts/AppDetailLayout';
import { appsApi } from '@/api/apps';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { EnvVar } from '@/types';
import { computeSlug } from '@/utils/slugify';

export function SettingsTab() {
  const { app, isLoading } = useAppDetail();
  const { appSlug } = useParams<{ appSlug: string }>();
  const qc = useQueryClient();

  const [name, setName] = useState(app?.name ?? '');
  const [description, setDescription] = useState('');
  const [envVars, setEnvVars] = useState<EnvVar[]>([]);
  const [maskedKeys, setMaskedKeys] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (app) setName(app.name);
  }, [app]);

  const updateMutation = useMutation({
    mutationFn: () => appsApi.updateApp(app!.id, { name }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['app', appSlug] }),
  });

  function addEnvVar() {
    setEnvVars((prev) => [...prev, { key: '', value: '', masked: false }]);
  }

  function removeEnvVar(idx: number) {
    setEnvVars((prev) => prev.filter((_, i) => i !== idx));
  }

  function toggleMask(key: string) {
    setMaskedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  if (isLoading || !app) return null;

  const slug = computeSlug(app.name);

  return (
    <div className="flex flex-col gap-5 max-w-2xl">
      {/* Identity */}
      <Card>
        <h2 className="text-sm font-medium text-foreground mb-4">Identité</h2>
        <div className="flex flex-col gap-3">
          <Input
            label="Nom d'affichage"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <Input
            label="Slug"
            value={slug}
            readOnly
            mono
            hint="Le slug est immuable."
            className="text-muted-foreground"
          />
          <Input
            label="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Description optionnelle"
          />
          <div className="flex justify-end">
            <Button
              variant="primary"
              size="sm"
              loading={updateMutation.isPending}
              onClick={() => updateMutation.mutate()}
              disabled={name === app.name}
            >
              Sauvegarder
            </Button>
          </div>
        </div>
      </Card>

      {/* Env vars */}
      <Card>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium text-foreground">Variables d'environnement</h2>
          <Button
            variant="ghost"
            size="sm"
            icon={<IconPlus size={13} />}
            onClick={addEnvVar}
          >
            Ajouter
          </Button>
        </div>

        {envVars.length === 0 ? (
          <p className="text-xs text-muted-foreground">Aucune variable.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {envVars.map((ev, i) => {
              const isMasked = maskedKeys.has(ev.key);
              return (
                <div key={i} className="flex items-center gap-2">
                  <Input
                    placeholder="CLE"
                    value={ev.key}
                    onChange={(e) => {
                      const next = [...envVars];
                      next[i] = { ...next[i], key: e.target.value };
                      setEnvVars(next);
                    }}
                    mono
                    className="flex-1"
                  />
                  <Input
                    placeholder="valeur"
                    value={ev.value}
                    type={isMasked ? 'password' : 'text'}
                    onChange={(e) => {
                      const next = [...envVars];
                      next[i] = { ...next[i], value: e.target.value };
                      setEnvVars(next);
                    }}
                    mono
                    className="flex-1"
                    suffix={
                      <button
                        type="button"
                        onClick={() => toggleMask(ev.key)}
                        className="text-muted-foreground"
                      >
                        {isMasked ? <IconEyeOff size={13} /> : <IconEye size={13} />}
                      </button>
                    }
                  />
                  <button
                    onClick={() => removeEnvVar(i)}
                    className="text-muted-foreground hover:text-danger transition-colors"
                  >
                    <IconTrash size={14} />
                  </button>
                </div>
              );
            })}
          </div>
        )}

        {envVars.length > 0 && (
          <>
            <p className="text-xs text-muted-foreground mt-3">
              Les modifications déclenchent un redeploy.
            </p>
            <div className="flex justify-end mt-3">
              <Button variant="primary" size="sm">
                Sauvegarder
              </Button>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
