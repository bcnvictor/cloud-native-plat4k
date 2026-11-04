import { render, screen, cleanup } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import {
  AUTH_WARNING_LABELS,
  EnvFromWarning,
  activationProblem,
} from '../pages/group/app/tabs/AuthWarnings';

afterEach(cleanup);

describe('EnvFromWarning', () => {
  it('shows the envFrom notice for chart_missing_envfrom', () => {
    render(<EnvFromWarning warnings={['keycloak_provisioning_failed', 'chart_missing_envfrom']} appSlug="demo" />);
    expect(screen.getByText('demo-env')).toBeTruthy();
    expect(screen.getByText('envFrom')).toBeTruthy();
    expect(screen.getByRole('link').getAttribute('href')).toBe('https://cnp-docs.pages.dev/guides/keycloak-app-auth/');
  });

  it('stays hidden for activation warnings', () => {
    const { container } = render(
      <EnvFromWarning
        warnings={['keycloak_instance_unavailable', 'keycloak_provisioning_failed', 'oidc_keys_conflict']}
        appSlug="demo"
      />
    );
    expect(container.innerHTML).toBe('');
  });
});

describe('activationProblem', () => {
  it('explains each activation warning', () => {
    expect(activationProblem(['oidc_keys_conflict'], false)).toBe(AUTH_WARNING_LABELS.oidc_keys_conflict);
    expect(activationProblem(['keycloak_instance_unavailable'], false)).toMatch(/platform admin/);
    expect(activationProblem(['keycloak_provisioning_failed'], false)).toBe(
      AUTH_WARNING_LABELS.keycloak_provisioning_failed
    );
  });

  it('does not blame a missing instance when Vault may be the one down', () => {
    // keycloak_instance_unavailable also covers Vault unreachable/sealed (the
    // provisioner secret and the OIDC_* check both live there).
    const label = AUTH_WARNING_LABELS.keycloak_instance_unavailable;
    expect(label).toMatch(/Vault/);
    expect(label).toMatch(/retry later/i);
    expect(label).not.toMatch(/no keycloak instance is configured/i);
  });

  it('falls back to the retry message when provisioning failed without a code', () => {
    expect(activationProblem([], false)).toBe(AUTH_WARNING_LABELS.keycloak_provisioning_failed);
  });

  it('reports nothing for a working activation, whatever the chart warning', () => {
    expect(activationProblem(['chart_missing_envfrom'], true)).toBeNull();
    expect(activationProblem(null, null)).toBeNull();
  });
});
