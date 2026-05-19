import type { ApplicationStatus, ResourceStatus } from '@/types';

export const APP_STATUS_MAP: Record<ApplicationStatus, ResourceStatus> = {
  deployed: 'running',
  onboarding: 'pending',
  ready: 'stopped',
};
