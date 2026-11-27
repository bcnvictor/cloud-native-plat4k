import { create } from 'zustand';
import { assistantApi } from '@/api/assistant';
import type { DoctorDiagnosis, DoctorEnv } from '@/types';

/**
 * État partagé du CNP Doctor.
 *
 * - `runs` : un diagnostic par application et environnement. La carte d'Overview et
 *   le panneau de l'assistant lisent la même entrée, donc un diagnostic lancé d'un
 *   côté s'affiche de l'autre.
 * - `mode` : tenue du robot (`chat` ou `doctor`). La bascule automatique ne remplace
 *   jamais un choix fait à la main sur l'application en cours (`manual`).
 */

export type RobotMode = 'chat' | 'doctor';

export type DoctorRunStatus = 'idle' | 'running' | 'done' | 'error';

export interface DoctorRun {
  status: DoctorRunStatus;
  data?: DoctorDiagnosis;
  error?: string;
  /** Horodatage (ms) du lancement, pour animer la progression. */
  startedAt?: number;
}

export interface DoctorFocusRequest {
  appId: number;
  env: DoctorEnv;
  /** Change à chaque demande : permet de rejouer le défilement vers la carte. */
  nonce: number;
}

interface DoctorState {
  runs: Record<string, DoctorRun>;
  mode: RobotMode;
  /** true quand l'utilisateur a choisi le mode à la main sur l'application en cours. */
  manual: boolean;
  /** Slug de l'application affichée, ou null hors d'une page d'application. */
  context: string | null;
  /** Demande d'amener la carte d'Overview à l'écran (bandeau « Diagnostiquer »). */
  focus: DoctorFocusRequest | null;

  diagnose: (appId: number, env: DoctorEnv) => Promise<void>;
  reset: (appId: number, env: DoctorEnv) => void;
  requestFocus: (appId: number, env: DoctorEnv) => void;
  /** La carte a traité la demande `nonce` : elle ne sera pas rejouée au prochain affichage. */
  clearFocus: (nonce: number) => void;

  /** Choix manuel (interrupteur du panneau) : prioritaire sur la bascule automatique. */
  setModeManual: (mode: RobotMode) => void;
  /** Bascule automatique vers le mode docteur, ignorée après un choix manuel. */
  autoDoctor: () => void;
  /** À appeler quand l'application affichée change : retour au chatbot, choix manuel oublié. */
  setContext: (context: string | null) => void;
}

export const doctorKey = (appId: number, env: DoctorEnv): string => `${appId}:${env}`;

const IDLE: DoctorRun = { status: 'idle' };

/** Sélecteur : le diagnostic d'une application et d'un environnement (jamais undefined). */
export const selectRun =
  (appId: number | undefined, env: DoctorEnv) =>
  (state: Pick<DoctorState, 'runs'>): DoctorRun =>
    (appId != null && state.runs[doctorKey(appId, env)]) || IDLE;

/** Message lisible à partir d'une erreur axios (champ `detail` de l'API) ou d'une erreur réseau. */
export function doctorErrorMessage(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  const status = (err as { response?: { status?: number } })?.response?.status;
  if (status === 403) {
    return 'Diagnosis requires the developer role or higher on this application.';
  }
  if (status === 503) return 'The AI assistant is disabled on this platform.';
  return 'The diagnosis could not be completed. Please try again in a moment.';
}

export const useDoctorStore = create<DoctorState>((set, get) => ({
  runs: {},
  mode: 'chat',
  manual: false,
  context: null,
  focus: null,

  diagnose: async (appId, env) => {
    const key = doctorKey(appId, env);
    if (get().runs[key]?.status === 'running') return;
    set((s) => ({
      runs: { ...s.runs, [key]: { status: 'running', startedAt: Date.now(), data: s.runs[key]?.data } },
    }));
    get().autoDoctor();
    try {
      const data = await assistantApi.diagnose(appId, env);
      set((s) => ({ runs: { ...s.runs, [key]: { status: 'done', data } } }));
    } catch (err) {
      set((s) => ({
        runs: { ...s.runs, [key]: { status: 'error', error: doctorErrorMessage(err) } },
      }));
    }
  },

  reset: (appId, env) =>
    set((s) => {
      const runs = { ...s.runs };
      delete runs[doctorKey(appId, env)];
      return { runs };
    }),

  requestFocus: (appId, env) => set({ focus: { appId, env, nonce: Date.now() } }),

  clearFocus: (nonce) => {
    if (get().focus?.nonce === nonce) set({ focus: null });
  },

  setModeManual: (mode) => set({ mode, manual: true }),

  autoDoctor: () => {
    if (!get().manual && get().mode !== 'doctor') set({ mode: 'doctor' });
  },

  setContext: (context) => {
    if (context === get().context) return;
    set({ context, manual: false, mode: 'chat' });
  },
}));
