import { render, screen, cleanup } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { AuthInstanceInfo } from '../pages/group/app/tabs/AuthInstanceInfo';

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
  it('shows unavailable instance without enabling actions', () => {
    render(<AuthInstanceInfo instance={{ ...instance, enabled: false }} />);
    expect(screen.getByText(/unavailable/i)).toBeTruthy();
    expect(screen.queryByRole('button')).toBeNull();
  });
});
