import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Step2Services } from '../pages/group/app/NewApp/Step2Services';
import { Step4Recap } from '../pages/group/app/NewApp/Step4Recap';
import type { ServiceConfig, Step1Data } from '@/types';

afterEach(cleanup);

const services = (database: boolean, password = ''): ServiceConfig => ({
  database: { enabled: database, dbName: '', pgSize: '5Gi', password },
  auth: { enabled: true },
});

const noop = () => {};

describe('Step2Services', () => {
  it('lets a new app select the database', () => {
    const onChange = vi.fn();
    render(<Step2Services data={services(false)} onChange={onChange} onNext={noop} onBack={noop} origin="scaffold" appName="demo-shop" />);

    const tile = screen.getByRole('button', { name: /Database/ });
    expect(tile.hasAttribute('disabled')).toBe(false);
    fireEvent.click(tile);
    expect(onChange).toHaveBeenCalledWith({ database: expect.objectContaining({ enabled: true }) });
  });

  it('shows the database settings once selected, name defaulting to the app name', () => {
    render(<Step2Services data={services(true)} onChange={noop} onNext={noop} onBack={noop} origin="scaffold" appName="demo-shop" />);

    expect(screen.getByPlaceholderText('demo_shop')).toBeTruthy();
    expect(screen.getByLabelText('Password')).toBeTruthy();
  });

  it('blocks Next on a password shorter than 12 characters', () => {
    const onNext = vi.fn();
    render(<Step2Services data={services(true, 'short')} onChange={noop} onNext={onNext} onBack={noop} origin="scaffold" />);

    expect(screen.getByText(/At least 12 characters/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(onNext).not.toHaveBeenCalled();
  });

  it('keeps the database unavailable for an existing repository', () => {
    const onChange = vi.fn();
    render(<Step2Services data={services(false)} onChange={onChange} onNext={noop} onBack={noop} origin="onboard" />);

    const tile = screen.getByRole('button', { name: /Database/ });
    expect(tile.hasAttribute('disabled')).toBe(true);
    expect(tile.textContent).toMatch(/New apps only/);
    fireEvent.click(tile);
    expect(onChange).not.toHaveBeenCalled();
  });

  it('keeps authentication selectable', () => {
    const onChange = vi.fn();
    render(<Step2Services data={services(false)} onChange={onChange} onNext={noop} onBack={noop} />);

    fireEvent.click(screen.getByRole('button', { name: /Authentication/ }));
    expect(onChange).toHaveBeenCalledWith({ auth: { enabled: false } });
  });
});

describe('Step4Recap', () => {
  const recap = (identity: Step1Data, svc: ServiceConfig) =>
    render(
      <Step4Recap
        identity={identity}
        services={svc}
        ciDeploy={{ trigger: 'on_commit', envVars: [], replicas: 1, targetClusterId: null, advancedOpen: false, expose: false }}
        onSubmit={noop}
        onBack={noop}
        isPending={false}
        error={null}
      />
    );

  it('lists the database of a new app, without its password', () => {
    recap({ origin: 'scaffold', name: 'demo', framework: 'go', repoUrl: '' }, services(true, 'correct-horse-battery'));
    expect(screen.getByText(/Database \(PostgreSQL 5Gi, your password\)/)).toBeTruthy();
    expect(screen.queryByText(/correct-horse-battery/)).toBeNull();
    expect(screen.getByText('Authentication (Keycloak)')).toBeTruthy();
  });

  it('never lists the database for an onboarded app', () => {
    recap({ origin: 'onboard', name: 'demo', framework: '', repoUrl: 'https://gitlab/x' }, services(true));
    expect(screen.queryByText(/PostgreSQL/)).toBeNull();
  });
});
