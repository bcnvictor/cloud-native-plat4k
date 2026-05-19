import { ResourceStatus } from '@/types';

interface StatusBadgeProps {
  status: ResourceStatus;
}

const LABEL: Record<ResourceStatus, string> = {
  running: 'Running',
  pending: 'En cours…',
  stopped: 'Arrêtée',
  terminated: 'Terminée',
  error: 'Échec',
};

export const StatusBadge = ({ status }: StatusBadgeProps) => (
  <div className="status-line">
    <span className={`status-dot ${status}`} />
    <span className={`status-text ${status}`}>{LABEL[status]}</span>
  </div>
);
