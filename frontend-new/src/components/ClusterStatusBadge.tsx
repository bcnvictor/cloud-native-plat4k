import { Badge } from '@/components/ui/Badge';
import type { ClusterConnection } from '@/types';

const STATUS_BADGE: Record<ClusterConnection['status'], {
  variant: 'success' | 'danger' | 'muted';
  label: string;
  pulse: boolean;
  border: string;
  dot: string;
}> = {
  online:  { variant: 'success', label: 'Online',  pulse: true,  border: 'border-success-border', dot: 'bg-success' },
  offline: { variant: 'danger',  label: 'Offline', pulse: false, border: 'border-danger-border',  dot: 'bg-danger' },
  unknown: { variant: 'muted',   label: 'Unknown', pulse: false, border: 'border-border',          dot: 'bg-zinc-400' },
};

export function ClusterStatusBadge({ status }: { status: ClusterConnection['status'] }) {
  const s = STATUS_BADGE[status] ?? STATUS_BADGE.unknown;
  return (
    <Badge variant={s.variant} className={`border ${s.border} gap-1.5 whitespace-nowrap`}>
      <span className="relative flex h-1.5 w-1.5 shrink-0">
        {s.pulse && (
          <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${s.dot} opacity-60`} />
        )}
        <span className={`relative inline-flex h-1.5 w-1.5 rounded-full ${s.dot}`} />
      </span>
      {s.label}
    </Badge>
  );
}
