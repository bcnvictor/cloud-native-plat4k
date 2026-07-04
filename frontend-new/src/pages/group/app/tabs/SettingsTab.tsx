import { useState, useEffect, useRef, useCallback } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams, useNavigate } from 'react-router-dom';
import { IconExternalLink, IconPlus, IconTrash } from '@tabler/icons-react';
import { useAppDetail } from '@/layouts/AppDetailLayout';
import { appsApi, EnvName } from '@/api/apps';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { Tabs } from '@/components/ui/Tabs';
import { ConfirmDialog } from '@/components/ConfirmDialog';
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
  const [deleteOpen, setDeleteOpen] = useState(false);

  const [envTab, setEnvTab] = useState<EnvName>('dev');
  const [showAddForm, setShowAddForm] = useState(false);
  const [addingKey, setAddingKey] = useState('');
  const [addingValue, setAddingValue] = useState('');
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editingValue, setEditingValue] = useState('');
  const [deletingVarKey, setDeletingVarKey] = useState<string | null>(null);

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

  const { data: myAccess } = useQuery({
    queryKey: ['myAccess', app?.id],
    queryFn: () => appsApi.getMyAccess(app!.id),
    enabled: !!app,
  });

  const { data: envVarsData, isLoading: envVarsLoading } = useQuery({
    queryKey: ['envVars', app?.id, envTab],
    queryFn: () => appsApi.listEnvVars(app!.id, envTab),
    enabled: !!app,
  });

  // Developer has zero access to prod, not even key names (ADR-0025 §3).
  const canSeeProd = !!myAccess && (myAccess.is_admin || myAccess.tier !== 'developer');
  const canWriteEnv = !!myAccess && (
    myAccess.is_admin ||
    (envTab === 'dev' ? myAccess.tier !== 'viewer' : myAccess.tier === 'maintainer' || myAccess.tier === 'owner')
  );

  useEffect(() => {
    if (envTab === 'prod' && myAccess && !canSeeProd) setEnvTab('dev');
  }, [myAccess, canSeeProd, envTab]);

  const invalidateEnvVars = () => qc.invalidateQueries({ queryKey: ['envVars', app?.id, envTab] });

  const setVarsMutation = useMutation({
    mutationFn: (variables: Record<string, string>) => appsApi.setEnvVars(app!.id, envTab, variables),
    onSuccess: invalidateEnvVars,
  });

  const deleteVarMutation = useMutation({
    mutationFn: (key: string) => appsApi.deleteEnvVar(app!.id, envTab, key),
    onSuccess: invalidateEnvVars,
  });

  function submitAddVar() {
    const key = addingKey.trim();
    if (!key) return;
    setVarsMutation.mutate(
      { [key]: addingValue },
      {
        onSuccess: () => {
          setAddingKey('');
          setAddingValue('');
          setShowAddForm(false);
          invalidateEnvVars();
        },
      }
    );
  }

  function submitEditVar(key: string) {
    if (!editingValue) return;
    setVarsMutation.mutate(
      { [key]: editingValue },
      {
        onSuccess: () => {
          setEditingKey(null);
          setEditingValue('');
          invalidateEnvVars();
        },
      }
    );
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
      <Card>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-medium text-foreground">Environment variables</h2>
          {canWriteEnv && !showAddForm && (
            <Button
              variant="ghost"
              size="sm"
              icon={<IconPlus size={13} />}
              onClick={() => setShowAddForm(true)}
            >
              Add
            </Button>
          )}
        </div>

        <Tabs
          tabs={
            canSeeProd
              ? [{ key: 'dev', label: 'dev' }, { key: 'prod', label: 'prod' }]
              : [{ key: 'dev', label: 'dev' }]
          }
          active={envTab}
          onChange={(k) => setEnvTab(k as EnvName)}
          className="mb-3"
        />

        {envVarsLoading ? (
          <p className="text-xs text-muted-foreground">Loading…</p>
        ) : (envVarsData?.keys.length ?? 0) === 0 && !showAddForm ? (
          <p className="text-xs text-muted-foreground">No variables.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {envVarsData?.keys.map((kv) => (
              <div key={kv.key} className="flex items-center gap-2">
                <span
                  className={cn('h-1.5 w-1.5 rounded-full shrink-0', kv.is_set ? 'bg-success' : 'bg-border')}
                  title={kv.is_set ? 'set' : 'unset'}
                />
                <span className="flex-1 text-sm font-mono text-foreground truncate">{kv.key}</span>
                {editingKey === kv.key ? (
                  <>
                    <Input
                      type="password"
                      placeholder="New value"
                      value={editingValue}
                      onChange={(e) => setEditingValue(e.target.value)}
                      mono
                      className="flex-1"
                      autoFocus
                    />
                    <Button
                      size="sm"
                      variant="primary"
                      loading={setVarsMutation.isPending}
                      disabled={!editingValue}
                      onClick={() => submitEditVar(kv.key)}
                    >
                      Save
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => { setEditingKey(null); setEditingValue(''); }}>
                      Cancel
                    </Button>
                  </>
                ) : (
                  canWriteEnv && (
                    <>
                      <Button size="sm" variant="ghost" onClick={() => { setEditingKey(kv.key); setEditingValue(''); }}>
                        Edit
                      </Button>
                      <button
                        onClick={() => setDeletingVarKey(kv.key)}
                        className="text-muted-foreground hover:text-danger transition-colors"
                      >
                        <IconTrash size={14} />
                      </button>
                    </>
                  )
                )}
              </div>
            ))}

            {showAddForm && (
              <div className="flex items-center gap-2 pt-2 mt-1 border-t border-border">
                <Input
                  placeholder="KEY"
                  value={addingKey}
                  onChange={(e) => setAddingKey(e.target.value)}
                  mono
                  className="flex-1"
                  autoFocus
                />
                <Input
                  type="password"
                  placeholder="value"
                  value={addingValue}
                  onChange={(e) => setAddingValue(e.target.value)}
                  mono
                  className="flex-1"
                />
                <Button
                  size="sm"
                  variant="primary"
                  loading={setVarsMutation.isPending}
                  disabled={!addingKey.trim()}
                  onClick={submitAddVar}
                >
                  Save
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => { setShowAddForm(false); setAddingKey(''); setAddingValue(''); }}
                >
                  Cancel
                </Button>
              </div>
            )}
          </div>
        )}

        <p className="text-xs text-muted-foreground mt-3">
          Values are never displayed once saved. Changes sync to the cluster within a few
          minutes and trigger a pod restart.
        </p>
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

      <ConfirmDialog
        open={!!deletingVarKey}
        onCancel={() => setDeletingVarKey(null)}
        onConfirm={() => {
          if (!deletingVarKey) return;
          deleteVarMutation.mutate(deletingVarKey, { onSuccess: () => setDeletingVarKey(null) });
        }}
        title="Delete variable"
        description={`Confirm deletion of "${deletingVarKey}" (${envTab}). The app will restart once the change propagates.`}
        confirmLabel="Delete"
        variant="danger"
        loading={deleteVarMutation.isPending}
      />
    </div>
  );
}
