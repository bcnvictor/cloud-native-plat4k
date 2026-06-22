import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { IconBrandDocker, IconCheck } from '@tabler/icons-react';
import { Step1Data } from '@/types';
import { appsApi } from '@/api/apps';
import { gitlabApi } from '@/api/gitlab';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { computeSlug } from '@/utils/slugify';
import { cn } from '@/utils/cn';

interface Props {
  data: Step1Data;
  onChange: (d: Partial<Step1Data>) => void;
  onNext: () => void;
  onCancel: () => void;
}

const ORIGINS: Array<{ value: 'scaffold' | 'onboard'; label: string; desc: string }> = [
  {
    value: 'scaffold',
    label: 'Scaffold',
    desc: 'Creates a new GitLab project from a template.',
  },
  {
    value: 'onboard',
    label: 'Onboard',
    desc: 'References an existing GitLab repo.',
  },
];

export function Step1Identity({ data, onChange, onNext, onCancel }: Props) {
  const { data: templates = [] } = useQuery({
    queryKey: ['templates'],
    queryFn: appsApi.listTemplates,
    enabled: data.origin === 'scaffold',
  });

  const { data: projects = [] } = useQuery({
    queryKey: ['gitlab-projects'],
    queryFn: gitlabApi.listProjects,
    enabled: data.origin === 'onboard',
  });

  const slug = useMemo(() => computeSlug(data.name), [data.name]);
  const isValid = data.name.length > 0;

  return (
    <div className="flex flex-col gap-5">
      {/* Origin cards */}
      <div className="grid grid-cols-2 gap-3">
        {ORIGINS.map((o) => {
          const selected = data.origin === o.value;
          return (
            <button
              key={o.value}
              onClick={() => onChange({ origin: o.value })}
              className={cn(
                'relative p-4 rounded-md border-2 text-left transition-colors',
                selected
                  ? 'border-primary bg-background'
                  : 'border-border bg-card hover:border-muted-foreground'
              )}
            >
              {selected && (
                <span className="absolute top-2 right-2 bg-[#007BA7] text-white rounded-full w-5 h-5 flex items-center justify-center">
                  <IconCheck size={11} strokeWidth={2.5} />
                </span>
              )}
              <IconBrandDocker size={20} className="text-muted-foreground mb-2" />
              <p className="text-sm font-medium text-foreground">{o.label}</p>
              <p className="text-xs text-muted-foreground mt-1">{o.desc}</p>
            </button>
          );
        })}
      </div>

      {/* Name + slug preview */}
      <div>
        <Input
          label="App name"
          value={data.name}
          onChange={(e) => onChange({ name: e.target.value })}
          placeholder="my-awesome-app"
          autoFocus
        />
        {data.name && (
          <p className="text-xs text-zinc-400 mt-1 font-mono">Slug: {slug}</p>
        )}
      </div>

      {/* Conditional: framework or repo */}
      {data.origin === 'scaffold' && templates.length > 0 && (
        <Select
          label="Framework"
          options={templates.map((t) => ({ value: t.path, label: t.name }))}
          value={data.framework}
          onChange={(v) => onChange({ framework: v })}
          placeholder="Choose a framework…"
        />
      )}

      {data.origin === 'scaffold' && templates.length === 0 && (
        <Select
          label="Framework"
          options={[
            { value: 'fastapi', label: 'FastAPI' },
            { value: 'nextjs', label: 'Next.js' },
            { value: 'django', label: 'Django' },
            { value: 'express', label: 'Express' },
          ]}
          value={data.framework}
          onChange={(v) => onChange({ framework: v })}
          placeholder="Choose a framework…"
        />
      )}

      {data.origin === 'onboard' && (
        <Select
          label="GitLab repo"
          options={
            projects.length > 0
              ? projects.map((p) => ({ value: p.web_url, label: p.full_path }))
              : [{ value: '', label: 'No projects available', disabled: true }]
          }
          value={data.repoUrl}
          onChange={(v) => onChange({ repoUrl: v })}
          placeholder="Select a repo…"
        />
      )}

      {/* Buttons */}
      <div className="flex justify-between mt-2">
        <Button variant="ghost" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button variant="primary" size="sm" disabled={!isValid} onClick={onNext}>
          Next
        </Button>
      </div>
    </div>
  );
}
