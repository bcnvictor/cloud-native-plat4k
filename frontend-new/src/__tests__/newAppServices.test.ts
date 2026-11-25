import { describe, expect, it } from 'vitest';
import { dbPasswordError, onboardServices, scaffoldingPayload } from '../pages/group/app/NewApp/services';
import type { ServiceConfig } from '@/types';

const step2 = (database: boolean, auth: boolean, db: Partial<ServiceConfig['database']> = {}): ServiceConfig => ({
  database: { enabled: database, dbName: '', pgSize: '5Gi', password: '', ...db },
  auth: { enabled: auth },
});

describe('scaffoldingPayload', () => {
  it('sends nothing when no service is selected', () => {
    expect(scaffoldingPayload(step2(false, false))).toBeUndefined();
  });

  it('sends keycloak alone without database settings', () => {
    expect(scaffoldingPayload(step2(false, true))).toEqual({ services: ['keycloak'] });
  });

  it('sends postgresql with its size, and name/password only when set', () => {
    expect(scaffoldingPayload(step2(true, false))).toEqual({ services: ['postgresql'], pg_size: '5Gi' });
    expect(scaffoldingPayload(step2(true, true, { dbName: 'shop', password: 'correct-horse-battery' }))).toEqual({
      services: ['postgresql', 'keycloak'],
      pg_size: '5Gi',
      db_name: 'shop',
      db_password: 'correct-horse-battery',
    });
  });
});

describe('onboardServices', () => {
  it('never sends postgresql for an existing repository', () => {
    expect(onboardServices(step2(true, true))).toEqual(['keycloak']);
    expect(onboardServices(step2(true, false))).toEqual([]);
  });
});

describe('dbPasswordError', () => {
  it('accepts an empty password (generated) and 12+ characters', () => {
    expect(dbPasswordError('')).toBeNull();
    expect(dbPasswordError('123456789012')).toBeNull();
    expect(dbPasswordError('short')).toMatch(/12 characters/);
  });
});
