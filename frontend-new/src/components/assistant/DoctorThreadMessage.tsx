import { IconRefresh } from '@tabler/icons-react';
import { DoctorDiagnosisView } from '@/components/doctor/DoctorDiagnosisView';
import { DoctorProgress } from '@/components/doctor/DoctorProgress';
import { selectRun, useDoctorStore, type RobotMode } from '@/store/doctor';
import type { DoctorEnv } from '@/types';
import { BotAvatar } from './Mascot';

interface Props {
  appId: number;
  env: DoctorEnv;
  appName?: string;
  /** Avatar du robot à côté du message (masqué si le robot graphique est désactivé). */
  showAvatar: boolean;
  mode: RobotMode;
}

/**
 * Diagnostic dans le fil de l'assistant. Le contenu vient du store partagé : un
 * diagnostic lancé depuis la carte d'Overview s'affiche ici à l'identique.
 */
export function DoctorThreadMessage({ appId, env, appName, showAvatar, mode }: Props) {
  const run = useDoctorStore(selectRun(appId, env));
  const relaunch = () => void useDoctorStore.getState().diagnose(appId, env);

  return (
    <div className="mb-3.5 animate-[msgIn_.28s_ease-out_both]" data-testid="doctor-thread-message">
      <div className="mb-1.5 flex items-center gap-[9px]">
        {showAvatar && <BotAvatar mode={mode} />}
        <span className="truncate text-xs font-medium text-muted-foreground">
          Diagnostic {env}
          {appName ? ` · ${appName}` : ''}
        </span>
      </div>
      <div className="w-full rounded-[4px_15px_15px_15px] border border-border bg-card p-3 text-[13px] text-foreground">
        {run.status === 'running' && <DoctorProgress startedAt={run.startedAt} compact />}
        {run.status === 'done' && run.data && (
          <DoctorDiagnosisView diagnosis={run.data} appId={appId} compact />
        )}
        {run.status === 'error' && (
          <div>
            <p className="text-[13px] leading-relaxed text-danger-text">{run.error}</p>
            <button
              type="button"
              onClick={relaunch}
              className="mt-2 inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:border-primary hover:text-primary"
            >
              <IconRefresh size={13} aria-hidden="true" />
              Réessayer
            </button>
          </div>
        )}
        {run.status === 'idle' && (
          <div>
            <p className="text-[13px] leading-relaxed text-muted-foreground">
              Ce diagnostic a été effacé.
            </p>
            <button
              type="button"
              onClick={relaunch}
              className="mt-2 inline-flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:border-primary hover:text-primary"
            >
              <IconRefresh size={13} aria-hidden="true" />
              Relancer le diagnostic
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
