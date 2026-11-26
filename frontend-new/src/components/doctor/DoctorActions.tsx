import { createContext, useContext, useEffect, useId, useRef, useState } from 'react';
import type { KeyboardEvent, ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  IconCircleCheck,
  IconCopy,
  IconExternalLink,
  IconFileText,
  IconGitCompare,
  IconHistory,
  IconLock,
  IconPipeline,
  IconPlayerPlay,
  IconRefresh,
  IconRotateClockwise,
  IconUserShare,
} from '@tabler/icons-react';
import { appsApi } from '@/api/apps';
import { Button } from '@/components/ui/Button';
import { toast } from '@/components/ui/toast';
import { useDoctorStore } from '@/store/doctor';
import type { DoctorAction, DoctorActionKind, DoctorDiagnosis } from '@/types';
import { cn } from '@/utils/cn';
import { CopyFallback, useCopyText } from './CopyFallback';
import {
  actionEnv,
  actionErrorMessage,
  diagnosisBasePath,
  maintainerRequestText,
  roleRequirement,
  rollbackTarget,
} from './doctorText';

const ICON: Record<DoctorActionKind, ReactNode> = {
  rollback: <IconRotateClockwise size={13} aria-hidden="true" />,
  resume: <IconPlayerPlay size={13} aria-hidden="true" />,
  view_logs: <IconFileText size={13} aria-hidden="true" />,
  view_history: <IconHistory size={13} aria-hidden="true" />,
  open_pipeline: <IconPipeline size={13} aria-hidden="true" />,
  open_repo_compare: <IconGitCompare size={13} aria-hidden="true" />,
  retry_later: <IconRefresh size={13} aria-hidden="true" />,
  contact_maintainer: <IconUserShare size={13} aria-hidden="true" />,
};

/** Les libellés d'action sont longs (« Revenir à la version a1b2c3d4 ») : ils peuvent passer à la ligne. */
const WRAP = 'h-auto min-h-7 max-w-full py-1 text-left';

const LINK_BASE =
  'inline-flex items-center justify-center gap-1 rounded-md px-2.5 text-xs font-medium ' + WRAP;
const LINK_VARIANT = {
  primary: 'bg-primary text-primary-foreground hover:bg-primary-hover active:bg-primary-active',
  secondary: 'bg-secondary text-foreground border border-border hover:bg-accent',
};

interface ItemProps {
  action: DoctorAction;
  diagnosis: DoctorDiagnosis;
  appId: number;
}

function usePageUrl(diagnosis: DoctorDiagnosis): { base: string | null; url: string | null } {
  const base = diagnosisBasePath(diagnosis);
  const url = base && typeof window !== 'undefined' ? `${window.location.origin}${base}` : null;
  return { base, url };
}

/** La justification n'accompagne que l'action principale : les autres restent des boutons. */
const ShowDescription = createContext(true);

function Description({ action }: { action: DoctorAction }) {
  const show = useContext(ShowDescription);
  return show && action.description ? (
    <p className="text-xs text-muted-foreground">{action.description}</p>
  ) : null;
}

/** Action non autorisée : désactivée, rôle requis visible, demande à copier. */
function RestrictedAction({ action, diagnosis }: ItemProps) {
  const roleId = useId();
  const { url } = usePageUrl(diagnosis);
  const { copy, fallback, dismiss } = useCopyText();

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant={action.primary ? 'primary' : 'secondary'}
          icon={ICON[action.kind]}
          disabled
          aria-describedby={roleId}
          className={WRAP}
        >
          {action.label}
        </Button>
        <Button
          size="sm"
          variant="secondary"
          icon={<IconCopy size={13} aria-hidden="true" />}
          onClick={() =>
            copy(maintainerRequestText(diagnosis, action, url), {
              title: 'Demande copiée',
              description: 'Collez-la dans un message à un maintainer de l’application.',
            })
          }
        >
          Copier la demande
        </Button>
      </div>
      <p id={roleId} className="flex items-center gap-1 text-xs font-medium text-foreground">
        <IconLock size={12} aria-hidden="true" className="shrink-0 text-muted-foreground" />
        {roleRequirement(action)}
      </p>
      <Description action={action} />
      {fallback && <CopyFallback text={fallback} onClose={dismiss} />}
    </>
  );
}

type Phase = 'idle' | 'confirming' | 'done';

/** Rollback ou relance : confirmation nommée en place, puis appel de la route existante. */
function ConfirmedAction({ action, diagnosis, appId }: ItemProps) {
  const queryClient = useQueryClient();
  const [phase, setPhase] = useState<Phase>('idle');
  const [error, setError] = useState<string | null>(null);
  // `Button` ne transmet pas de ref : on retrouve le bouton dans son conteneur.
  const containerRef = useRef<HTMLDivElement>(null);
  const restoreFocus = useRef(false);
  const questionId = useId();

  const env = actionEnv(action, diagnosis);
  const isRollback = action.kind === 'rollback';
  const target = rollbackTarget(action, diagnosis);
  const historyId = action.params.history_id;
  const missingTarget = isRollback && historyId == null;

  const mutation = useMutation({
    mutationFn: async () => {
      if (isRollback) await appsApi.rollback(appId, historyId as number, env);
      else await appsApi.resumeApp(appId, env);
    },
    onSuccess: () => {
      toast(
        isRollback
          ? { title: `Rollback ${env} lancé`, description: `La version ${target} est en cours de déploiement.` }
          : { title: `Relance de ${env} lancée`, description: 'Les réplicas sont remis en service.' }
      );
      // L'état live (/status) met à jour le statut enregistré de l'application ; on relit
      // ensuite l'application pour que l'en-tête et le bandeau d'erreur suivent sans attendre.
      void queryClient
        .invalidateQueries({ queryKey: ['app-status', appId] })
        .then(() => queryClient.invalidateQueries({ queryKey: ['app'] }));
      queryClient.invalidateQueries({ queryKey: ['app-history', appId] });
      if (!isRollback) queryClient.invalidateQueries({ queryKey: ['app-scale-state', appId] });
      setError(null);
      setPhase('done');
    },
    onError: (err) => {
      setError(
        actionErrorMessage(
          err,
          isRollback
            ? 'Le rollback n’a pas pu être lancé. Réessayez dans un instant, ou passez par l’onglet History.'
            : 'La relance n’a pas pu être lancée. Réessayez dans un instant.'
        )
      );
      restoreFocus.current = true;
      setPhase('idle');
    },
  });

  useEffect(() => {
    const find = (sel: string) => containerRef.current?.querySelector<HTMLButtonElement>(sel);
    if (phase === 'confirming') find('[data-doctor-cancel]')?.focus();
    // Le bouton de confirmation disparaît : sans ça, le focus clavier retombe sur la page.
    if (phase === 'done') find('[data-doctor-recheck]')?.focus();
    if (phase === 'idle' && restoreFocus.current) {
      restoreFocus.current = false;
      find('[data-doctor-trigger]')?.focus();
    }
  }, [phase]);

  const cancel = () => {
    if (mutation.isPending) return;
    restoreFocus.current = true;
    setPhase('idle');
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      cancel();
    }
  };

  if (phase === 'done') {
    return (
      <div ref={containerRef} role="status" className="flex flex-wrap items-center gap-2">
        <span className="flex items-center gap-1.5 text-xs font-medium text-success-text">
          <IconCircleCheck size={14} aria-hidden="true" className="shrink-0" />
          {isRollback
            ? `Rollback lancé : ${target} est en cours de déploiement en ${env}.`
            : `Relance lancée : l’environnement ${env} redémarre.`}
        </span>
        <Button
          data-doctor-recheck
          size="sm"
          variant="secondary"
          icon={<IconRefresh size={13} aria-hidden="true" />}
          onClick={() => useDoctorStore.getState().diagnose(appId, env)}
        >
          Revérifier l’état
        </Button>
      </div>
    );
  }

  if (phase === 'confirming') {
    return (
      <div
        ref={containerRef}
        role="group"
        aria-labelledby={questionId}
        onKeyDown={onKeyDown}
        className="flex flex-col gap-2"
      >
        <p id={questionId} className="text-sm font-medium text-foreground">
          {isRollback
            ? `Revenir à ${target} pour ${diagnosis.app_name} en ${env} ? La version en panne sera remplacée.`
            : `Relancer l’environnement ${env} de ${diagnosis.app_name} ? Les réplicas seront remis en service.`}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant={isRollback ? 'danger' : 'primary'}
            icon={ICON[action.kind]}
            loading={mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {isRollback ? `Revenir à ${target}` : `Relancer ${env}`}
          </Button>
          <Button data-doctor-cancel size="sm" variant="ghost" onClick={cancel} disabled={mutation.isPending}>
            Annuler
          </Button>
          <span className="text-xs text-muted-foreground">Échap pour annuler</span>
        </div>
      </div>
    );
  }

  return (
    <>
      <div ref={containerRef} className="flex flex-wrap items-center gap-2">
        <Button
          data-doctor-trigger
          size="sm"
          variant={action.primary ? 'primary' : 'secondary'}
          icon={ICON[action.kind]}
          disabled={missingTarget}
          className={WRAP}
          onClick={() => {
            setError(null);
            setPhase('confirming');
          }}
        >
          {action.label}
        </Button>
      </div>
      <Description action={action} />
      {missingTarget && (
        <p className="text-xs text-muted-foreground">
          Version cible inconnue : choisissez-la dans l’onglet History.
        </p>
      )}
      {error && (
        <p role="alert" className="text-xs text-danger-text">
          {error}
        </p>
      )}
    </>
  );
}

/** Ouvre l'onglet Logs ou History de l'application. */
function TabAction({ action, diagnosis }: ItemProps) {
  const navigate = useNavigate();
  const { base } = usePageUrl(diagnosis);
  const tab = action.kind === 'view_logs' ? 'logs' : 'history';
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant={action.primary ? 'primary' : 'secondary'}
          icon={ICON[action.kind]}
          disabled={!base}
          className={WRAP}
          onClick={() =>
            base &&
            // Les logs s'ouvrent sur l'environnement diagnostiqué (l'onglet part sinon sur dev).
            navigate(tab === 'logs' ? `${base}/logs?env=${diagnosis.env}` : `${base}/${tab}`)
          }
        >
          {action.label}
        </Button>
      </div>
      <Description action={action} />
    </>
  );
}

/** Lien externe : pipeline ou comparaison GitLab. */
function LinkAction({ action }: ItemProps) {
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        {action.url ? (
          <a
            href={action.url}
            target="_blank"
            rel="noopener noreferrer"
            className={cn(LINK_BASE, LINK_VARIANT[action.primary ? 'primary' : 'secondary'])}
          >
            <span className="shrink-0">{ICON[action.kind]}</span>
            {action.label}
            <IconExternalLink size={12} aria-hidden="true" className="shrink-0 opacity-70" />
            <span className="sr-only"> (nouvel onglet)</span>
          </a>
        ) : (
          <Button size="sm" variant="secondary" icon={ICON[action.kind]} disabled className={WRAP}>
            {action.label}
          </Button>
        )}
      </div>
      <Description action={action} />
    </>
  );
}

function RetryAction({ action, diagnosis, appId }: ItemProps) {
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant={action.primary ? 'primary' : 'secondary'}
          icon={ICON[action.kind]}
          className={WRAP}
          onClick={() => useDoctorStore.getState().diagnose(appId, diagnosis.env)}
        >
          {action.label}
        </Button>
      </div>
      <Description action={action} />
    </>
  );
}

/** Contacter un maintainer : la demande (constat, cause, action conseillée) est copiée. */
function ContactAction({ action, diagnosis }: ItemProps) {
  const { url } = usePageUrl(diagnosis);
  const { copy, fallback, dismiss } = useCopyText();
  const recommended =
    diagnosis.actions.find((a) => a.primary && a.kind !== 'contact_maintainer') ??
    diagnosis.actions.find((a) => !a.allowed && a.kind !== 'contact_maintainer');
  return (
    <>
      <p className="text-xs font-medium text-foreground">{action.label}</p>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant={action.primary ? 'primary' : 'secondary'}
          icon={<IconCopy size={13} aria-hidden="true" />}
          onClick={() =>
            copy(maintainerRequestText(diagnosis, recommended, url), {
              title: 'Demande copiée',
              description: 'Collez-la dans un message à un maintainer de l’application.',
            })
          }
        >
          Copier la demande
        </Button>
      </div>
      <Description action={action} />
      {fallback && <CopyFallback text={fallback} onClose={dismiss} />}
    </>
  );
}

function ActionBody(props: ItemProps) {
  const { action } = props;
  if (action.kind === 'contact_maintainer') return <ContactAction {...props} />;
  if (!action.allowed) return <RestrictedAction {...props} />;
  switch (action.kind) {
    case 'rollback':
    case 'resume':
      return <ConfirmedAction {...props} />;
    case 'view_logs':
    case 'view_history':
      return <TabAction {...props} />;
    case 'open_pipeline':
    case 'open_repo_compare':
      return <LinkAction {...props} />;
    case 'retry_later':
      return <RetryAction {...props} />;
    default:
      return <Description action={action} />;
  }
}

/**
 * Actions proposées par la plateforme : l'action principale seule sur sa ligne, avec sa
 * justification, puis les autres côte à côte.
 */
export function DoctorActions({ diagnosis, appId }: { diagnosis: DoctorDiagnosis; appId: number }) {
  const actions = [...diagnosis.actions].sort((a, b) => Number(b.primary) - Number(a.primary));
  if (actions.length === 0) return null;
  return (
    <ul className="flex flex-wrap items-start gap-2">
      {actions.map((action) => (
        <li
          key={action.id}
          className={cn('flex min-w-0 max-w-full flex-col gap-1.5', action.primary && 'basis-full')}
        >
          <ShowDescription.Provider value={action.primary}>
            <ActionBody action={action} diagnosis={diagnosis} appId={appId} />
          </ShowDescription.Provider>
        </li>
      ))}
    </ul>
  );
}
