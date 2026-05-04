import { clsx } from 'clsx';
import { ResourceStatus } from '@/types';

interface StatusBadgeProps {
  status: ResourceStatus;
}

export const StatusBadge = ({ status }: StatusBadgeProps) => {
  const styles = {
    pending: 'bg-yellow-100 text-yellow-800',
    running: 'bg-green-100 text-green-800',
    stopped: 'bg-gray-100 text-gray-800',
    terminated: 'bg-red-100 text-red-800',
    error: 'bg-red-100 text-red-800',
  };

  return (
    <span className={clsx('px-2.5 py-0.5 rounded-full text-xs font-medium capitalize', styles[status])}>
      {status}
    </span>
  );
};
