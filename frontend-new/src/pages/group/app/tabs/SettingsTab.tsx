import { useState, useEffect, useRef, useCallback } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams, useNavigate } from 'react-router-dom';
import { IconExternalLink, IconEye, IconEyeOff, IconPlus, IconTrash } from '@tabler/icons-react';
import { useAppDetail } from '@/layouts/AppDetailLayout';
import { appsApi } from '@/api/apps';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { EnvVar } from '@/types';
import { appUrl } from '@/utils/appUrls';
import { cn } from '@/utils/cn';

export function SettingsTab() {
  const { app, isLoading } = useAppDetail();
  const { slug, appSlug } = useParams<{ slug: string; appSlug: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const [name, setName] = useState(app?.name ?? '');
  const [description, setDescription] = useState(app?.description ?? '');
  const [expose, setExpose] = useState(app?.expose ?? false);
  const descRef = useRef<HTMLTextAreaElement>(null);

  const autoResize = useCallback(() => {
    const el = descRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, []);
  const [envVars, setEnvVars] = useState<EnvVar[]>([]);
  const [maskedKeys, setMaskedKeys] = useState<Set<string>>(new Set());
  const [deleteOpen, setDeleteOpen] = useState(false);

  useEffect(() => {
    if (app) {
      setName(app.name);
      setDescription(app.description ?? '');
      setExpose(app.expose ?? false);
      setTimeout(autoResize, 0);
    }
  }, [app, autoResize]);

  const updateMutation = useMutation({
    mutationFn: () => appsApi.updateApp(app!.id, { name, description: description || undefined }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['app', appSlug] }),
  });

  const deleteMutation = useMutation({
    mutationFn: () => appsApi.deleteApp(app!.id),
    onSuccess: () => navigate(`/groups/${slug}/apps`),
  });

  const exposeMutation = useMutation({
    mutationFn: (newExpose: boolean) => appsApi.toggleExpose(app!.id, newExpose),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['app', appSlug] }),
    onError: () => setExpose(app?.expose ?? false),
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

  const appSlugComputed = app.slug;

  return (
    <div className="flex flex-col gap-5 max-w-2xl">
      {/* Identity */}
      <Card>
        <h2 className="text-sm font-medium text-foreground mb-4">Identity</h2>
        <div className="flex flex-col gap-3">
          <Input
            label="Display name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <Input
            label="Slug"
            value={appSlugComputed}
            readOnly
            mono
            hint="The slug is immutable."
            className="text-muted-foreground"
          />
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">Description</label>
            <textarea
              ref={descRef}
              value={description}
              onChange={(e) => { setDescription(e.target.value); autoResize(); }}
              placeholder="Optional description"
              rows={2}
              className="w-full resize-none overflow-hidden rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
          <div className="flex justify-end">
            <Button
              variant="primary"
              size="sm"
              loading={updateMutation.isPending}
              onClick={() => updateMutation.mutate()}
              disabled={name === app.name && description === (app.description ?? '')}
            >
              Save
            </Button>
          </div>
        </div>
      </Card>

      {/* Env vars */}
      {/* MOCK: getEnvVars/updateEnvVars sont des stubs côté api/apps.ts — décommissionner quand le backend expose GET/PUT /apps/:id/envvars */}
      <Card>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium text-foreground">Environment variables</h2>
          <Button
            variant="ghost"
            size="sm"
            icon={<IconPlus size={13} />}
            onClick={addEnvVar}
          >
            Add
          </Button>
        </div>

        {envVars.length === 0 ? (
          <p className="text-xs text-muted-foreground">No variables.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {envVars.map((ev, i) => {
              const isMasked = maskedKeys.has(ev.key);
              return (
                <div key={i} className="flex items-center gap-2">
                  <Input
                    placeholder="KEY"
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
                    placeholder="value"
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
              Changes trigger a redeploy.
            </p>
            <div className="flex justify-end mt-3">
              <Button variant="primary" size="sm">
                Save
              </Button>
            </div>
          </>
        )}
      </Card>

      {/* Internet exposure */}
      <Card>
        <h2 className="text-sm font-medium text-foreground mb-4">Internet exposure</h2>
        <div className="flex items-start gap-3">
          <button
            onClick={() => {
              const next = !expose;
              setExpose(next);
              exposeMutation.mutate(next);
            }}
            disabled={exposeMutation.isPending}
            className={cn(
              'relative mt-0.5 h-5 w-9 shrink-0 rounded-full border-2 transition-colors',
              expose ? 'bg-info border-info' : 'bg-border border-border'
            )}
          >
            <span
              className={cn(
                'absolute top-0.5 h-3 w-3 rounded-full bg-white shadow transition-transform',
                expose ? 'translate-x-4' : 'translate-x-0.5'
              )}
            />
          </button>
          <div className="flex flex-col gap-1">
            <p className="text-sm font-medium text-foreground">
              {expose ? 'Exposed on internet' : 'Port-forward only'}
            </p>
            {expose && app.slug ? (
              <div className="flex flex-col gap-0.5">
                <a
                  href={appUrl(app.slug, 'prod')}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs font-mono text-[#007BA7] hover:underline flex items-center gap-1"
                >
                  {appUrl(app.slug, 'prod')}
                  <IconExternalLink size={10} />
                </a>
                <a
                  href={appUrl(app.slug, 'dev')}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs font-mono text-[#007BA7] hover:underline flex items-center gap-1"
                >
                  {appUrl(app.slug, 'dev')}
                  <IconExternalLink size={10} />
                </a>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">
                Enable to expose the app on <span className="font-mono">cloud-native-plat4k.me</span> subdomains.
              </p>
            )}
          </div>
        </div>
      </Card>

      {/* Danger Zone */}
      <Card className="border-danger/30">
        <h2 className="text-sm font-medium text-danger mb-1">Danger zone</h2>
        <p className="text-xs text-muted-foreground mb-4">
          Deletion is irreversible.
          {app.origin === 'scaffold' && ' The associated GitLab repository will also be deleted.'}
        </p>
        <Button variant="danger" size="sm" onClick={() => setDeleteOpen(true)}>
          Delete this app
        </Button>
      </Card>

      <ConfirmDialog
        open={deleteOpen}
        onCancel={() => setDeleteOpen(false)}
        onConfirm={() => deleteMutation.mutate()}
        title="Delete app"
        description={`Confirm deletion of "${app.name}". This action is irreversible.`}
        confirmLabel="Delete"
        variant="danger"
        loading={deleteMutation.isPending}
      />
    </div>
  );
}
