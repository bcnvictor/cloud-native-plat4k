import { render, screen, cleanup, fireEvent, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Step2Services } from '../pages/group/app/NewApp/Step2Services';
import { Step4Recap } from '../pages/group/app/NewApp/Step4Recap';
import type { ServiceConfig } from '@/types';

afterEach(cleanup);

const services = (database: boolean): ServiceConfig => ({
  database: { enabled: database, dbName: 'app_db', pgSize: '5Gi' },
  auth: { enabled: true },
  cache: { enabled: false },
});

describe('Step2Services', () => {
  it('greys out the database tile, available through the CLI/API only', () => {
    const onChange = vi.fn();
    render(<Step2Services data={services(false)} onChange={onChange} onNext={() => {}} onBack={() => {}} />);

    const tile = screen.getByRole('button', { name: /Database/ });
    expect(tile.hasAttribute('disabled')).toBe(true);
    expect(tile.textContent).toMatch(/CLI\/API only/);
    fireEvent.click(tile);
    expect(onChange).not.toHaveBeenCalled();
  });

  it('badges the database "CLI/API", not "Soon", and the cache "Soon"', () => {
    render(<Step2Services data={services(false)} onChange={() => {}} onNext={() => {}} onBack={() => {}} />);

    const database = screen.getByRole('button', { name: /Database/ });
    expect(within(database).getByText('CLI/API')).toBeTruthy();
    expect(within(database).queryByText('Soon')).toBeNull();
    const cache = screen.getByRole('button', { name: /Cache/ });
    expect(within(cache).getByText('Soon')).toBeTruthy();
    expect(cache.hasAttribute('disabled')).toBe(true);
  });

  it('keeps authentication selectable', () => {
    const onChange = vi.fn();
    render(<Step2Services data={services(false)} onChange={onChange} onNext={() => {}} onBack={() => {}} />);

    fireEvent.click(screen.getByRole('button', { name: /Authentication/ }));
    expect(onChange).toHaveBeenCalledWith({ auth: { enabled: false } });
  });
});

describe('Step4Recap', () => {
  it('never lists the database, which the wizard does not send', () => {
    render(
      <Step4Recap
        identity={{ origin: 'scaffold', name: 'demo', framework: 'go', repoUrl: '' }}
        services={services(true)}
        ciDeploy={{
          trigger: 'on_commit',
          envVars: [],
          replicas: 1,
          targetClusterId: null,
          advancedOpen: false,
          expose: false,
        }}
        onSubmit={() => {}}
        onBack={() => {}}
        isPending={false}
        error={null}
      />
    );
    expect(screen.queryByText(/PostgreSQL/)).toBeNull();
    expect(screen.getByText('Authentication (Keycloak)')).toBeTruthy();
  });
});
