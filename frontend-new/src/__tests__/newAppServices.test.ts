import { describe, expect, it } from 'vitest';
import { requestedServices } from '../pages/group/app/NewApp/services';
import type { ServiceConfig } from '@/types';

const step2 = (database: boolean, auth: boolean): ServiceConfig => ({
  database: { enabled: database, dbName: 'app_db', pgSize: '5Gi' },
  auth: { enabled: auth },
  cache: { enabled: false },
});

describe('requestedServices', () => {
  it('sends keycloak when authentication is selected', () => {
    expect(requestedServices(step2(false, true))).toEqual(['keycloak']);
  });

  it('sends nothing when no wired service is selected', () => {
    expect(requestedServices(step2(false, false))).toEqual([]);
  });

  it('does not send postgresql from the wizard', () => {
    expect(requestedServices(step2(true, true))).toEqual(['keycloak']);
    expect(requestedServices(step2(true, false))).toEqual([]);
  });
});
