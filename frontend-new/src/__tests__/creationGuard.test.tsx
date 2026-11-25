import { useRef } from 'react';
import { act, cleanup, render, screen } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { createMemoryRouter, RouterProvider, useNavigate } from 'react-router-dom';
import { CreationOverlay, useCreationGuard } from '../pages/group/app/NewApp/CreationOverlay';

afterEach(cleanup);

// Le data router (requis par useBlocker) construit une Request par navigation : celle de
// Node refuse l'AbortSignal de jsdom. Le routeur n'a besoin que de l'URL et du signal.
const NativeRequest = globalThis.Request;
beforeAll(() => {
  globalThis.Request = class {
    url: string;
    signal?: AbortSignal;
    method: string;
    constructor(input: string | URL, init?: RequestInit) {
      this.url = String(input);
      this.signal = init?.signal ?? undefined;
      this.method = init?.method ?? 'GET';
    }
  } as unknown as typeof Request;
});
afterAll(() => {
  globalThis.Request = NativeRequest;
});

let release: () => void = () => {};
let go: (to: string) => void = () => {};

function Wizard() {
  const creating = useRef(true);
  const navigate = useNavigate();
  useCreationGuard(creating, true);
  release = () => { creating.current = false; };
  go = (to) => navigate(to);
  return <CreationOverlay appName="demo-shop" />;
}

function setup() {
  const router = createMemoryRouter(
    [
      { path: '/new', element: <Wizard /> },
      { path: '/elsewhere', element: <p>Elsewhere</p> },
      { path: '/app', element: <p>App page</p> },
    ],
    { initialEntries: ['/new'] },
  );
  render(<RouterProvider router={router} />);
  return router;
}

describe('creation guard', () => {
  it('shows a blocking overlay while the app is created', () => {
    setup();
    const dialog = screen.getByRole('alertdialog');
    expect(dialog.getAttribute('aria-busy')).toBe('true');
    expect(dialog.textContent).toMatch(/Creating demo-shop/);
  });

  it('blocks navigation away during creation, then lets the final redirect through', async () => {
    const router = setup();

    await act(async () => go('/elsewhere'));
    expect(router.state.location.pathname).toBe('/new');

    release();
    await act(async () => go('/app'));
    expect(router.state.location.pathname).toBe('/app');
  });
});
