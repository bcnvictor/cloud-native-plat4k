import { IconMoon, IconHandStop } from '@tabler/icons-react';
import { Badge } from '@/components/ui/Badge';
import type { AppScaleStateResponse } from '@/types';

interface AppScaleBadgeProps {
  scale: AppScaleStateResponse | null | undefined;
}

/** Small header indicator for a stopped env. Prod takes priority over dev when both are stopped. */
export function AppScaleBadge({ scale }: AppScaleBadgeProps) {
  if (!scale) return null;

  const prodStopped = scale.prod?.is_stopped;
  const state = prodStopped ? scale.prod : scale.dev?.is_stopped ? scale.dev : null;
  if (!state) return null;

  const envLabel = prodStopped ? 'prod' : 'dev';
  const scheduled = state.stop_reason === 'schedule';

  return (
    <Badge variant={scheduled ? 'info' : 'warning'} className="gap-1">
      {scheduled ? <IconMoon size={11} /> : <IconHandStop size={11} />}
      {scheduled ? `Sleeping (${envLabel})` : `Stopped (${envLabel}, manual)`}
    </Badge>
  );
}
