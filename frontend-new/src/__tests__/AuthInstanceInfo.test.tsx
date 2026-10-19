import { render, screen, cleanup } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { AuthInstanceInfo, canActivateAuth } from '../pages/group/app/tabs/AuthInstanceInfo';

afterEach(cleanup);
const instance = { instance_key: 'private-01', cluster_id: 2, cluster_name: 'Private cloud', public_url: 'https://auth.cloud-native-plat4k.me/clusters/private-01', enabled: true, source: 'cluster' as const };

describe('AuthInstanceInfo', () => {
  it('shows bound cluster and issuer', () => {
    render(<AuthInstanceInfo instance={instance} />);
    expect(screen.getByText('private-01')).toBeTruthy();
    expect(screen.getByText(/Private cloud/)).toBeTruthy();
    expect(screen.getByRole('link').getAttribute('href')).toBe('https://auth.cloud-native-plat4k.me/clusters/private-01');
  });
  it('labels legacy instance', () => {
    render(<AuthInstanceInfo instance={{ ...instance, instance_key: null, source: 'legacy' }} />);
    expect(screen.getByText(/Legacy configuration/)).toBeTruthy();
  });
  it('tells to contact an admin when the instance is disabled', () => {
    render(<AuthInstanceInfo instance={{ ...instance, enabled: false }} />);
    expect(screen.getByText(/unavailable.*platform administrator/i)).toBeTruthy();
  });
  it('says when no instance is configured', () => {
    render(<AuthInstanceInfo instance={null} />);
    expect(screen.getByText('No Keycloak instance configured.')).toBeTruthy();
    expect(screen.queryByRole('link')).toBeNull();
  });
});

describe('canActivateAuth', () => {
  it('needs an enabled instance, cluster or legacy', () => {
    expect(canActivateAuth(instance)).toBe(true);
    expect(canActivateAuth({ ...instance, instance_key: null, source: 'legacy' })).toBe(true);
    expect(canActivateAuth({ ...instance, enabled: false })).toBe(false);
    expect(canActivateAuth(null)).toBe(false);
    expect(canActivateAuth(undefined)).toBe(false); // status still loading
  });
});
