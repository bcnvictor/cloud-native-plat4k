import { useEffect, type MutableRefObject } from 'react';
import { useBlocker } from 'react-router-dom';
import { Spinner } from '@/components/ui/Spinner';

/**
 * Pendant la création, la requête continue côté serveur même si on quitte la page :
 * repo GitLab, CI et gitops se créent quand même, et la redirection finale ramènerait
 * de force sur l'app. L'overlay couvre toute l'interface (sidebar comprise), la
 * navigation du routeur (précédent/suivant du navigateur) est bloquée et fermer ou
 * recharger l'onglet demande confirmation.
 *
 * `creating` est un ref et non l'état de la mutation : la redirection vers l'app part
 * du onSuccess, quand la mutation est encore « pending » — le ref est relâché juste avant.
 */
export function useCreationGuard(creating: MutableRefObject<boolean>, active: boolean) {
  const blocker = useBlocker(() => creating.current);

  useEffect(() => {
    // On reste sur la page : rien à confirmer, la création finira par rediriger.
    if (blocker.state === 'blocked') blocker.reset();
  }, [blocker]);

  useEffect(() => {
    if (!active) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [active]);
}

export function CreationOverlay({ appName }: { appName: string }) {
  return (
    <div
      role="alertdialog"
      aria-modal="true"
      aria-busy="true"
      aria-labelledby="creation-overlay-title"
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm"
    >
      <div className="flex w-full max-w-sm flex-col items-center gap-4 rounded-xl border border-border bg-background px-8 py-7 text-center shadow-xl">
        <Spinner size="lg" />
        <div className="flex flex-col gap-1.5">
          <h2 id="creation-overlay-title" className="text-base font-semibold text-foreground">
            Creating {appName}…
          </h2>
          <p className="text-sm text-muted-foreground">
            Setting up the GitLab repository, the CI pipeline and the deployment manifests.
            This can take up to a minute.
          </p>
          <p className="text-xs text-muted-foreground">Keep this page open — you will be redirected to the app.</p>
        </div>
      </div>
    </div>
  );
}
