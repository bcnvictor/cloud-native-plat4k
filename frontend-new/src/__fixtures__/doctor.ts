/**
 * Exemples de diagnostics CNP Doctor, pour les tests et le développement de l'interface.
 * Ils suivent le contrat de `src/types/doctor.ts` ; les valeurs reprennent le scénario
 * de démo (application `demo-shop`, version saine a1b2c3d4, version en panne f4e5d6c7).
 */
import type { DoctorDiagnosis } from '@/types';

const AI_USED = {
  used: true,
  provider: 'gemini',
  model: 'gemini-flash-latest',
  input_tokens: 1840,
  output_tokens: 260,
  estimated_cost_usd: 0.0009,
  error: null,
} as const;

const AI_UNUSED = {
  used: false,
  provider: null,
  model: null,
  input_tokens: 0,
  output_tokens: 0,
  estimated_cost_usd: null,
  error: null,
} as const;

/** Régression après déploiement, vue par un maintainer : rollback autorisé. */
export const REGRESSION_DIAGNOSIS: DoctorDiagnosis = {
  app_id: 7,
  app_name: 'demo-shop',
  app_slug: 'demo-shop',
  group_slug: 'team-demo',
  env: 'prod',
  generated_at: '2026-11-16T14:07:31Z',
  verdict: 'regression',
  source: 'ai',
  headline: "demo-shop redémarre en boucle en prod depuis le déploiement de 14 h 01.",
  explanation:
    "La version f4e5d6c7 plante au démarrage : elle attend la variable PAYMENT_API_URL, absente de la configuration. " +
    "La version précédente a1b2c3d4 a tourné 3 jours sans incident. Le plus rapide est de revenir à cette version, puis de corriger le commit.",
  cause: {
    summary: 'Le dernier déploiement lit une variable de configuration qui n’existe pas (PAYMENT_API_URL).',
    confidence: 'haute',
    category: 'deployment',
  },
  evidence: [
    {
      id: 'E1',
      source: 'kubernetes',
      label: 'Pod demo-shop-7d9f8b6c5-x2k4q : CrashLoopBackOff, 6 redémarrages',
      detail: 'Dernier arrêt : Error (code 1) à 14:06:48. Back-off restarting failed container.',
      at: '2026-11-16T14:02:11Z',
      url: null,
      cited: true,
    },
    {
      id: 'E2',
      source: 'logs',
      label: "KeyError: 'PAYMENT_API_URL' (×6 sur la dernière heure)",
      detail:
        '14:02:10 [ERROR] Traceback (most recent call last):\n' +
        '14:02:10 [ERROR]   File "/app/app/config.py", line 22, in load\n' +
        "14:02:10 [ERROR] KeyError: 'PAYMENT_API_URL'\n" +
        '14:02:10 [ERROR] Application startup failed. Exiting.',
      at: '2026-11-16T14:02:10Z',
      url: null,
      cited: true,
    },
    {
      id: 'E3',
      source: 'deployments',
      label: 'Déploiement de f4e5d6c7 en prod à 14:01, 1 minute avant la panne',
      detail: null,
      at: '2026-11-16T14:01:02Z',
      url: null,
      cited: true,
    },
    {
      id: 'E4',
      source: 'argocd',
      label: 'ArgoCD : sync Synced, santé Degraded',
      detail: null,
      at: '2026-11-16T14:05:00Z',
      url: null,
      cited: false,
    },
    {
      id: 'E5',
      source: 'git',
      label: 'Commit f4e5d6c7 : « feat(payment): nouveau client de paiement »',
      detail: 'Fichiers modifiés : app/config.py, app/payment/client.py, requirements.txt',
      at: '2026-11-16T13:52:40Z',
      url: 'https://gitlab.example.com/cnp-apps/team-demo/demo-shop/-/commit/f4e5d6c7',
      cited: true,
    },
    {
      id: 'E6',
      source: 'ci',
      label: 'Dernier pipeline #482 : success (branche main)',
      detail: null,
      at: '2026-11-16T13:58:12Z',
      url: 'https://gitlab.example.com/cnp-apps/team-demo/demo-shop/-/pipelines/482',
      cited: false,
    },
  ],
  timeline: {
    entries: [
      {
        at: '2026-11-13T13:20:00Z',
        kind: 'deployment',
        label: 'Déploiement de a1b2c3d4',
        revision: 'a1b2c3d4',
        history_id: 11,
        suspect: false,
        healthy: true,
      },
      {
        at: '2026-11-16T14:01:02Z',
        kind: 'deployment',
        label: 'Déploiement de f4e5d6c7',
        revision: 'f4e5d6c7',
        history_id: 12,
        suspect: true,
        healthy: false,
      },
      {
        at: '2026-11-16T14:02:10Z',
        kind: 'failure_onset',
        label: 'Premier redémarrage du conteneur',
        revision: null,
        history_id: null,
        suspect: false,
        healthy: null,
      },
      {
        at: '2026-11-16T14:05:00Z',
        kind: 'degraded',
        label: 'Application marquée dégradée',
        revision: null,
        history_id: null,
        suspect: false,
        healthy: null,
      },
    ],
    suspect: { history_id: 12, revision: 'f4e5d6c7', deployed_at: '2026-11-16T14:01:02Z', ran_for_seconds: null },
    last_healthy: {
      history_id: 11,
      revision: 'a1b2c3d4',
      deployed_at: '2026-11-13T13:20:00Z',
      ran_for_seconds: 261662,
    },
    onset_at: '2026-11-16T14:02:10Z',
    onset_delay_seconds: 68,
    correlation: 'haute',
  },
  changes: {
    from_revision: 'a1b2c3d4',
    to_revision: 'f4e5d6c7',
    compare_url: 'https://gitlab.example.com/cnp-apps/team-demo/demo-shop/-/compare/a1b2c3d4...f4e5d6c7',
    commits: [
      {
        sha: 'f4e5d6c7',
        title: 'feat(payment): nouveau client de paiement',
        author: 'Alice Martin',
        at: '2026-11-16T13:52:40Z',
        url: 'https://gitlab.example.com/cnp-apps/team-demo/demo-shop/-/commit/f4e5d6c7',
      },
      {
        sha: '9c8b7a6d',
        title: 'chore: mise à jour des dépendances',
        author: 'Alice Martin',
        at: '2026-11-16T11:14:03Z',
        url: 'https://gitlab.example.com/cnp-apps/team-demo/demo-shop/-/commit/9c8b7a6d',
      },
    ],
    files: [
      { path: 'app/config.py', change: 'modified' },
      { path: 'app/payment/client.py', change: 'added' },
      { path: 'requirements.txt', change: 'modified' },
    ],
    truncated: false,
    unavailable_reason: null,
  },
  actions: [
    {
      id: 'A1',
      kind: 'rollback',
      label: 'Revenir à la version a1b2c3d4',
      description: 'Dernière version saine : elle a tourné 3 jours sans incident.',
      primary: true,
      allowed: true,
      required_role: 'maintainer',
      params: { env: 'prod', history_id: 11, revision: 'a1b2c3d4' },
      url: null,
    },
    {
      id: 'A2',
      kind: 'open_repo_compare',
      label: 'Voir ce qui a changé sur GitLab',
      description: 'Comparer a1b2c3d4 et f4e5d6c7 pour corriger le commit.',
      primary: false,
      allowed: true,
      required_role: null,
      params: {},
      url: 'https://gitlab.example.com/cnp-apps/team-demo/demo-shop/-/compare/a1b2c3d4...f4e5d6c7',
    },
    {
      id: 'A3',
      kind: 'view_logs',
      label: 'Voir les logs',
      description: 'Lire les erreurs complètes dans l’onglet Logs.',
      primary: false,
      allowed: true,
      required_role: null,
      params: { env: 'prod' },
      url: null,
    },
  ],
  missing_signals: [],
  raw_text: null,
  ai: AI_USED,
  user_role: 'maintainer',
};

/** Même régression, vue par un developer : le rollback est affiché mais non autorisé. */
export const REGRESSION_AS_DEVELOPER: DoctorDiagnosis = {
  ...REGRESSION_DIAGNOSIS,
  actions: REGRESSION_DIAGNOSIS.actions.map((a) =>
    a.kind === 'rollback' ? { ...a, allowed: false } : a
  ),
  user_role: 'developer',
};

/** Le fournisseur IA n'a pas répondu : diagnostic établi par la plateforme seule. */
export const FALLBACK_DIAGNOSIS: DoctorDiagnosis = {
  ...REGRESSION_DIAGNOSIS,
  source: 'rules_fallback',
  headline: 'demo-shop est en échec en prod depuis le déploiement de f4e5d6c7 (14 h 01).',
  explanation: null,
  cause: {
    summary: 'Régression probable du dernier déploiement : la panne a commencé 1 minute après.',
    confidence: 'haute',
    category: 'deployment',
  },
  evidence: REGRESSION_DIAGNOSIS.evidence.map((e) => ({
    ...e,
    cited: ['E1', 'E2', 'E3'].includes(e.id),
  })),
  ai: { ...AI_UNUSED, provider: 'gemini', model: 'gemini-flash-latest', error: 'quota' },
};

/** Cas évident : rien à signaler, aucun appel IA. */
export const HEALTHY_DIAGNOSIS: DoctorDiagnosis = {
  app_id: 7,
  app_name: 'demo-shop',
  app_slug: 'demo-shop',
  group_slug: 'team-demo',
  env: 'prod',
  generated_at: '2026-11-16T15:10:00Z',
  verdict: 'healthy',
  source: 'rules',
  headline: 'demo-shop fonctionne normalement en prod : rien à signaler.',
  explanation: null,
  cause: null,
  evidence: [
    {
      id: 'E1',
      source: 'argocd',
      label: 'ArgoCD : sync Synced, santé Healthy',
      detail: null,
      at: '2026-11-16T15:09:40Z',
      url: null,
      cited: true,
    },
    {
      id: 'E2',
      source: 'kubernetes',
      label: '2/2 réplicas prêts, aucun redémarrage',
      detail: null,
      at: null,
      url: null,
      cited: true,
    },
    {
      id: 'E3',
      source: 'logs',
      label: 'Aucune ligne d’erreur sur la dernière heure',
      detail: null,
      at: null,
      url: null,
      cited: true,
    },
  ],
  timeline: null,
  changes: null,
  actions: [],
  missing_signals: [],
  raw_text: null,
  ai: AI_UNUSED,
  user_role: 'developer',
};

/** Cas évident : environnement arrêté volontairement. */
export const STOPPED_DIAGNOSIS: DoctorDiagnosis = {
  ...HEALTHY_DIAGNOSIS,
  env: 'dev',
  verdict: 'stopped',
  headline: 'demo-shop n’est pas en panne en dev : l’environnement est arrêté depuis hier 19 h 00.',
  evidence: [
    {
      id: 'E1',
      source: 'platform',
      label: 'Environnement dev arrêté (arrêt planifié) depuis le 15/11 à 19:00',
      detail: null,
      at: '2026-11-15T19:00:00Z',
      url: null,
      cited: true,
    },
  ],
  actions: [
    {
      id: 'A1',
      kind: 'resume',
      label: 'Relancer l’environnement dev',
      description: 'Remet les réplicas en service.',
      primary: true,
      allowed: false,
      required_role: 'maintainer',
      params: { env: 'dev' },
      url: null,
    },
  ],
};

/** L'application tourne, mais le dernier pipeline a échoué : la nouvelle version n'est pas déployée. */
export const CI_FAILURE_DIAGNOSIS: DoctorDiagnosis = {
  ...HEALTHY_DIAGNOSIS,
  verdict: 'ci_failure',
  source: 'ai',
  headline: 'demo-shop tourne en prod, mais ton dernier commit n’est pas déployé : le pipeline a échoué.',
  explanation:
    'Le job « test » du pipeline #483 a échoué sur une assertion. La version en service reste a1b2c3d4.',
  cause: {
    summary: 'Le test test_checkout_total échoue : total attendu 42.00, obtenu 41.99.',
    confidence: 'haute',
    category: 'ci',
  },
  evidence: [
    {
      id: 'E1',
      source: 'ci',
      label: 'Pipeline #483 en échec : job « test » (stage test)',
      detail:
        'FAILED tests/test_checkout.py::test_checkout_total - AssertionError: assert 41.99 == 42.00\n' +
        '1 failed, 57 passed in 12.31s',
      at: '2026-11-16T15:01:00Z',
      url: 'https://gitlab.example.com/cnp-apps/team-demo/demo-shop/-/pipelines/483',
      cited: true,
    },
    {
      id: 'E2',
      source: 'argocd',
      label: 'ArgoCD : sync Synced, santé Healthy',
      detail: null,
      at: '2026-11-16T15:09:40Z',
      url: null,
      cited: true,
    },
  ],
  actions: [
    {
      id: 'A1',
      kind: 'open_pipeline',
      label: 'Ouvrir le pipeline #483',
      description: 'Lire le log complet du job en échec.',
      primary: true,
      allowed: true,
      required_role: null,
      params: {},
      url: 'https://gitlab.example.com/cnp-apps/team-demo/demo-shop/-/pipelines/483',
    },
  ],
  ai: AI_USED,
};

/** Signaux insuffisants : la plateforme dit ce qui manque au lieu de deviner. */
export const INCONCLUSIVE_DIAGNOSIS: DoctorDiagnosis = {
  ...HEALTHY_DIAGNOSIS,
  verdict: 'inconclusive',
  headline: 'Je n’ai pas assez de signaux pour diagnostiquer demo-shop en prod.',
  evidence: [],
  missing_signals: [
    { source: 'kubernetes', reason: 'Kubernetes injoignable (délai dépassé).' },
    { source: 'argocd', reason: 'ArgoCD injoignable (délai dépassé).' },
  ],
  actions: [
    {
      id: 'A1',
      kind: 'retry_later',
      label: 'Réessayer dans une minute',
      description: 'Les sources de signaux ne répondent pas pour le moment.',
      primary: true,
      allowed: true,
      required_role: null,
      params: {},
      url: null,
    },
  ],
};
