import { useQuery } from '@tanstack/react-query';
import { IconStethoscope } from '@tabler/icons-react';
import { assistantApi } from '@/api/assistant';
import { useDoctorStore } from '@/store/doctor';
import type { DoctorEnv } from '@/types';
import { cn } from '@/utils/cn';

interface Props {
  appId: number;
  env: DoctorEnv;
  appName?: string;
  /** Appelé avant la demande (ex. : revenir sur l'onglet Overview). */
  onBeforeLaunch?: () => void;
  className?: string;
}

/**
 * « Diagnostiquer » : amène la carte CNP Doctor à l'écran et lance le diagnostic.
 * Masqué quand l'assistant IA est désactivé (même règle que la carte).
 */
export function DoctorLaunchButton({ appId, env, appName, onBeforeLaunch, className }: Props) {
  const { data: uiSettings } = useQuery({
    queryKey: ['ai-ui-settings'],
    queryFn: assistantApi.getUiSettings,
    retry: false,
  });
  if (!uiSettings?.assistant_enabled) return null;

  const launch = () => {
    onBeforeLaunch?.();
    const store = useDoctorStore.getState();
    store.requestFocus(appId, env);
    void store.diagnose(appId, env);
  };

  return (
    <button
      type="button"
      onClick={launch}
      aria-label={appName ? `Diagnostiquer ${appName} en ${env}` : `Diagnostiquer ${env}`}
      className={cn(
        'inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium',
        'text-primary hover:bg-primary-subtle',
        className
      )}
    >
      <IconStethoscope size={13} aria-hidden="true" />
      Diagnostiquer
    </button>
  );
}
