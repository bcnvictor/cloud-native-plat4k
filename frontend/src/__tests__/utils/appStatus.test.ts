import { describe, it, expect } from 'vitest';
import { APP_STATUS_MAP } from '@/utils/appStatus';

describe('APP_STATUS_MAP', () => {
  it('mappe deployed → running', () => {
    expect(APP_STATUS_MAP['deployed']).toBe('running');
  });

  it('mappe onboarding → pending', () => {
    expect(APP_STATUS_MAP['onboarding']).toBe('pending');
  });

  it('mappe ready → stopped', () => {
    expect(APP_STATUS_MAP['ready']).toBe('stopped');
  });

  it('couvre tous les statuts ApplicationStatus', () => {
    const keys = Object.keys(APP_STATUS_MAP);
    expect(keys).toContain('deployed');
    expect(keys).toContain('onboarding');
    expect(keys).toContain('ready');
  });
});
