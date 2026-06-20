import { Application, AppHealthStatus } from '@/types';

export function getAppHealth(app: Application): AppHealthStatus {
  switch (app.status) {
    case 'onboarding': return 'provisioning';
    case 'ready': return 'stopped';
    case 'deployed': return 'healthy';
    default: return 'stopped';
  }
}

export const STATUS_LABEL: Record<AppHealthStatus, string> = {
  healthy: 'Healthy',
  deploying: 'Deploying',
  updating: 'Updating',
  unhealthy: 'Unhealthy',
  stopped: 'Stopped',
  provisioning: 'Provisioning',
};

export const STATUS_COLOR: Record<AppHealthStatus, string> = {
  healthy: 'text-success-text bg-success-subtle',
  deploying: 'text-info-text bg-info-subtle',
  updating: 'text-info-text bg-info-subtle',
  unhealthy: 'text-danger-text bg-danger-subtle',
  stopped: 'text-muted-foreground bg-muted',
  provisioning: 'text-amber-700 bg-amber-50 border border-amber-200',
};

export const STATUS_DOT: Record<AppHealthStatus, string> = {
  healthy: 'bg-success',
  deploying: 'bg-info',
  updating: 'bg-info',
  unhealthy: 'bg-danger',
  stopped: 'bg-muted-foreground',
  provisioning: 'bg-muted-foreground',
};
