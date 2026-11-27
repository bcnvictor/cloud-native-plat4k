import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { assistantApi } from '@/api/assistant';
import { doctorErrorMessage, doctorKey, selectRun, useDoctorStore } from '@/store/doctor';
import { REGRESSION_DIAGNOSIS } from '@/__fixtures__/doctor';

function resetStore() {
  useDoctorStore.setState({ runs: {}, mode: 'chat', manual: false, context: null, focus: null });
}

beforeEach(resetStore);
afterEach(() => vi.restoreAllMocks());

describe('store du CNP Doctor', () => {
  it('lance un diagnostic, le range par application et environnement, et passe le robot en docteur', async () => {
    const spy = vi.spyOn(assistantApi, 'diagnose').mockResolvedValue(REGRESSION_DIAGNOSIS);

    const pending = useDoctorStore.getState().diagnose(7, 'prod');
    expect(selectRun(7, 'prod')(useDoctorStore.getState()).status).toBe('running');
    expect(useDoctorStore.getState().mode).toBe('doctor');
    await pending;

    const run = selectRun(7, 'prod')(useDoctorStore.getState());
    expect(spy).toHaveBeenCalledWith(7, 'prod');
    expect(run.status).toBe('done');
    expect(run.data?.verdict).toBe('regression');
    // l'autre environnement n'est pas touché
    expect(selectRun(7, 'dev')(useDoctorStore.getState()).status).toBe('idle');
    expect(doctorKey(7, 'prod')).toBe('7:prod');
  });

  it("n'appelle pas deux fois l'API pour un diagnostic déjà en cours", async () => {
    let release: (v: typeof REGRESSION_DIAGNOSIS) => void = () => {};
    const spy = vi
      .spyOn(assistantApi, 'diagnose')
      .mockReturnValue(new Promise((resolve) => (release = resolve)));

    const first = useDoctorStore.getState().diagnose(7, 'prod');
    await useDoctorStore.getState().diagnose(7, 'prod');
    release(REGRESSION_DIAGNOSIS);
    await first;

    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("garde le message de l'API en cas d'erreur", async () => {
    vi.spyOn(assistantApi, 'diagnose').mockRejectedValue({
      response: { status: 403, data: { detail: 'Accès refusé pour ce rôle.' } },
    });

    await useDoctorStore.getState().diagnose(7, 'prod');

    const run = selectRun(7, 'prod')(useDoctorStore.getState());
    expect(run.status).toBe('error');
    expect(run.error).toBe('Accès refusé pour ce rôle.');
    expect(doctorErrorMessage({ response: { status: 503 } })).toMatch(/disabled/);
    expect(doctorErrorMessage(new Error('réseau'))).toMatch(/try again/);
  });

  it('ne remplace pas un choix manuel par la bascule automatique', () => {
    const s = useDoctorStore.getState();
    s.setContext('demo-shop');
    s.autoDoctor();
    expect(useDoctorStore.getState().mode).toBe('doctor');

    s.setModeManual('chat');
    s.autoDoctor();
    expect(useDoctorStore.getState().mode).toBe('chat');
  });

  it("revient au chatbot et oublie le choix manuel quand l'application change", () => {
    const s = useDoctorStore.getState();
    s.setContext('demo-shop');
    s.setModeManual('doctor');

    s.setContext(null);
    expect(useDoctorStore.getState()).toMatchObject({ mode: 'chat', manual: false, context: null });

    s.setContext('other-app');
    s.autoDoctor();
    expect(useDoctorStore.getState().mode).toBe('doctor');
  });

  it("n'efface la demande de focus que si c'est celle qui a été traitée", () => {
    vi.spyOn(Date, 'now').mockReturnValueOnce(10).mockReturnValueOnce(20);
    const s = useDoctorStore.getState();
    s.requestFocus(7, 'prod');
    s.requestFocus(7, 'dev');                // une nouvelle demande arrive entre-temps
    s.clearFocus(10);
    expect(useDoctorStore.getState().focus?.env).toBe('dev');
    s.clearFocus(20);
    expect(useDoctorStore.getState().focus).toBeNull();
  });

  it('émet une nouvelle demande de focus à chaque appel', () => {
    vi.spyOn(Date, 'now').mockReturnValueOnce(1).mockReturnValueOnce(2);
    useDoctorStore.getState().requestFocus(7, 'prod');
    const first = useDoctorStore.getState().focus;
    useDoctorStore.getState().requestFocus(7, 'prod');
    expect(useDoctorStore.getState().focus?.nonce).not.toBe(first?.nonce);
  });
});
