import { useEffect, useId, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { IconRefresh, IconStethoscope } from '@tabler/icons-react';
import { assistantApi } from '@/api/assistant';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { useAppStatus } from '@/hooks/useAppStatus';
import { selectRun, useDoctorStore } from '@/store/doctor';
import type { AppRuntimeStatus, ArgoEnvStatus, DoctorEnv } from '@/types';
import { cn } from '@/utils/cn';
import { DoctorDiagnosisView } from './DoctorDiagnosisView';
import { DoctorProgress } from './DoctorProgress';
import { bringIntoView, prefersReducedMotion } from './doctorText';

const ENVS: DoctorEnv[] = ['prod', 'dev'];

function isBroken(s: ArgoEnvStatus | null | undefined): boolean {
  return !!s?.health_status && ['Degraded', 'Missing'].includes(s.health_status);
}

/** L'environnement en erreur ; prod quand les deux (ou aucun) le sont. */
export function defaultDoctorEnv(status: AppRuntimeStatus | undefined): DoctorEnv {
  return isBroken(status?.argocd_dev) && !isBroken(status?.argocd_prod) ? 'dev' : 'prod';
}

function EnvSelector({
  value,
  onChange,
  broken,
}: {
  value: DoctorEnv;
  onChange: (env: DoctorEnv) => void;
  broken: Record<DoctorEnv, boolean>;
}) {
  const group = useRef<HTMLDivElement>(null);

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key)) return;
    e.preventDefault();
    const next: DoctorEnv = value === 'prod' ? 'dev' : 'prod';
    onChange(next);
    group.current?.querySelector<HTMLButtonElement>(`[data-env="${next}"]`)?.focus();
  };

  return (
    <div
      ref={group}
      role="radiogroup"
      aria-label="Environnement à diagnostiquer"
      onKeyDown={onKeyDown}
      className="inline-flex rounded-md border border-border bg-background-subtle p-0.5"
    >
      {ENVS.map((env) => {
        const checked = env === value;
        return (
          <button
            key={env}
            type="button"
            role="radio"
            data-env={env}
            aria-checked={checked}
            tabIndex={checked ? 0 : -1}
            onClick={() => onChange(env)}
            className={cn(
              'inline-flex h-6 items-center gap-1.5 rounded-sm px-2.5 text-xs font-medium',
              checked ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
            )}
          >
            {broken[env] && <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-danger" />}
            {env}
            {broken[env] && <span className="sr-only"> (en erreur)</span>}
          </button>
        );
      })}
    </div>
  );
}

/**
 * Carte CNP Doctor de l'onglet Overview : choix de l'environnement, lancement,
 * progression, résultat ou erreur. L'état vit dans le store partagé avec le panneau
 * de l'assistant.
 */
export function DoctorCard({ appId, appName }: { appId: number; appName: string }) {
  const { data: uiSettings } = useQuery({
    queryKey: ['ai-ui-settings'],
    queryFn: assistantApi.getUiSettings,
    retry: false,
  });
  const visible = !!uiSettings?.assistant_enabled;
  const { data: status } = useAppStatus(appId);

  const prodRun = useDoctorStore(selectRun(appId, 'prod'));
  const devRun = useDoctorStore(selectRun(appId, 'dev'));
  const focus = useDoctorStore((s) => s.focus);

  /** null tant que l'utilisateur n'a pas choisi : on suit l'état de l'application. */
  const [chosen, setChosen] = useState<DoctorEnv | null>(null);
  const autoEnv: DoctorEnv =
    (prodRun.status !== 'idle') !== (devRun.status !== 'idle')
      ? prodRun.status !== 'idle'
        ? 'prod'
        : 'dev'
      : defaultDoctorEnv(status);
  const env = chosen ?? autoEnv;
  const run = env === 'prod' ? prodRun : devRun;

  const wrapper = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const titleId = useId();

  // Bandeau ou carte d'environnement « Diagnostiquer » : basculer et amener la carte à l'écran.
  useEffect(() => {
    if (!visible || !focus || focus.appId !== appId) return;
    setChosen(focus.env);
    const el = wrapper.current;
    if (el) bringIntoView(el, prefersReducedMotion() ? 'auto' : 'smooth');
    titleRef.current?.focus({ preventScroll: true });
    // Demande traitée : ne pas la rejouer au prochain affichage de l'onglet.
    useDoctorStore.getState().clearFocus(focus.nonce);
  }, [focus, appId, visible]);

  if (!visible) return null;

  const launch = () => void useDoctorStore.getState().diagnose(appId, env);
  const running = run.status === 'running';
  const done = run.status === 'done' && !!run.data;

  return (
    <div ref={wrapper} className="scroll-mt-4">
      <Card className="hover:translate-y-0 hover:shadow-sm">
        <section aria-labelledby={titleId} className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2
              id={titleId}
              ref={titleRef}
              tabIndex={-1}
              className="flex items-center gap-1.5 rounded-sm text-sm font-medium text-foreground"
            >
              <IconStethoscope size={14} aria-hidden="true" />
              CNP Doctor
            </h2>
            <div className="flex flex-wrap items-center gap-2">
              <EnvSelector
                value={env}
                onChange={setChosen}
                broken={{ prod: isBroken(status?.argocd_prod), dev: isBroken(status?.argocd_dev) }}
              />
              {done ? (
                <Button size="sm" variant="ghost" icon={<IconRefresh size={13} aria-hidden="true" />} onClick={launch}>
                  Relancer
                </Button>
              ) : run.status !== 'error' ? (
                <Button
                  size="sm"
                  variant="primary"
                  icon={<IconStethoscope size={13} aria-hidden="true" />}
                  disabled={running}
                  onClick={launch}
                >
                  {`Diagnostiquer ${env}`}
                </Button>
              ) : null}
            </div>
          </div>

          {running ? (
            <DoctorProgress key={`${env}-${run.startedAt ?? 0}`} startedAt={run.startedAt} />
          ) : run.status === 'error' ? (
            <div className="flex flex-col items-start gap-2">
              <p role="alert" className="text-sm text-danger-text">
                {run.error}
              </p>
              <Button size="sm" variant="secondary" icon={<IconRefresh size={13} aria-hidden="true" />} onClick={launch}>
                Réessayer
              </Button>
            </div>
          ) : done && run.data ? (
            <DoctorDiagnosisView diagnosis={run.data} appId={appId} />
          ) : (
            <p className="text-sm text-muted-foreground">
              Vérifie l’état de {appName} en croisant pods, logs, ArgoCD, pipeline et derniers
              déploiements, puis explique la panne preuves à l’appui ; rien n’est modifié sans votre accord.
            </p>
          )}
        </section>
      </Card>
    </div>
  );
}
