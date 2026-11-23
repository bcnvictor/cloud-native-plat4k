/**
 * CNP Doctor — contrat de `POST /apps/{id}/doctor/diagnose`.
 * Miroir des schémas de `backend/api/routes/doctor.py` et des énumérations
 * `Doctor*` de `shared/models.py`.
 */
import type { CnpTier } from './index';

export type DoctorEnv = 'prod' | 'dev';

/** Décidé par la plateforme, jamais par l'IA. */
export type DoctorVerdict =
  // sans appel IA
  | 'healthy'
  | 'stopped'
  | 'cluster_offline'
  | 'deploying'
  | 'not_deployed'
  | 'inconclusive'
  // avec appel IA
  | 'regression'
  | 'failing'
  | 'ci_failure'
  | 'unstable';

/** rules : verdict évident sans IA · ai : rédigé par l'IA et vérifié · rules_fallback : l'IA n'a pas répondu. */
export type DoctorSource = 'rules' | 'ai' | 'rules_fallback';

export type DoctorConfidence = 'haute' | 'moyenne' | 'faible';

export type DoctorCauseCategory =
  | 'deployment'
  | 'config'
  | 'resources'
  | 'image'
  | 'dependency'
  | 'platform'
  | 'ci'
  | 'unknown';

export type DoctorActionKind =
  | 'rollback'
  | 'resume'
  | 'view_logs'
  | 'open_pipeline'
  | 'view_history'
  | 'open_repo_compare'
  | 'retry_later'
  | 'contact_maintainer';

export type DoctorEvidenceSource =
  | 'kubernetes'
  | 'logs'
  | 'argocd'
  | 'ci'
  | 'deployments'
  | 'events'
  | 'git'
  | 'platform';

export type DoctorTimelineKind =
  | 'deployment'
  | 'rollback'
  | 'failure_onset'
  | 'degraded'
  | 'recovered'
  | 'pipeline_failed';

export type DoctorAIError = 'quota' | 'provider_error' | 'unreachable' | 'limit';

/** Une preuve du registre construit par la plateforme. `cited` : retenue par le diagnostic. */
export interface DoctorEvidence {
  id: string;
  source: DoctorEvidenceSource;
  label: string;
  /** Texte long (lignes de log, message Kubernetes), ou null. */
  detail: string | null;
  at: string | null;
  url: string | null;
  cited: boolean;
}

export interface DoctorTimelineEntry {
  at: string;
  kind: DoctorTimelineKind;
  label: string;
  revision: string | null;
  history_id: number | null;
  /** Déploiement désigné comme responsable. */
  suspect: boolean;
  /** true : version saine connue · false : version en panne · null : inconnu ou sans objet. */
  healthy: boolean | null;
}

export interface DoctorDeploymentRef {
  history_id: number;
  revision: string;
  deployed_at: string;
  /** Durée de service avant d'être remplacée (dernière version saine uniquement). */
  ran_for_seconds: number | null;
}

export interface DoctorTimeline {
  entries: DoctorTimelineEntry[];
  suspect: DoctorDeploymentRef | null;
  last_healthy: DoctorDeploymentRef | null;
  onset_at: string | null;
  /** Délai entre le déploiement suspect et le premier signal d'échec. */
  onset_delay_seconds: number | null;
  correlation: DoctorConfidence | null;
}

export interface DoctorCommit {
  sha: string;
  title: string;
  author: string | null;
  at: string | null;
  url: string | null;
}

export interface DoctorFileChange {
  path: string;
  change: 'added' | 'modified' | 'deleted' | 'renamed';
}

export interface DoctorChanges {
  from_revision: string;
  to_revision: string;
  compare_url: string | null;
  commits: DoctorCommit[];
  files: DoctorFileChange[];
  truncated: boolean;
  /** Renseigné quand la comparaison n'a pas pu être lue (commits et files sont alors vides). */
  unavailable_reason: string | null;
}

export interface DoctorActionParams {
  env?: DoctorEnv;
  history_id?: number;
  revision?: string;
}

export interface DoctorAction {
  id: string;
  kind: DoctorActionKind;
  label: string;
  description: string;
  primary: boolean;
  /** L'utilisateur courant a-t-il le droit de la lancer ? */
  allowed: boolean;
  required_role: CnpTier | null;
  params: DoctorActionParams;
  /** Lien externe (pipeline, comparaison GitLab), ou null pour une action interne. */
  url: string | null;
}

export interface DoctorMissingSignal {
  source: DoctorEvidenceSource;
  reason: string;
}

export interface DoctorCause {
  summary: string;
  confidence: DoctorConfidence;
  category: DoctorCauseCategory;
}

export interface DoctorAIInfo {
  used: boolean;
  provider: string | null;
  model: string | null;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number | null;
  error: DoctorAIError | null;
}

export interface DoctorDiagnosis {
  app_id: number;
  app_name: string;
  /** Page de l'application diagnostiquée : /groups/{group_slug}/apps/{app_slug}. */
  app_slug: string;
  /** Null si l'application n'est rattachée à aucun groupe connu. */
  group_slug: string | null;
  env: DoctorEnv;
  generated_at: string;
  verdict: DoctorVerdict;
  source: DoctorSource;
  /** Le constat, en une phrase. */
  headline: string;
  /** Ce qui s'est passé, en deux à quatre phrases. */
  explanation: string | null;
  cause: DoctorCause | null;
  evidence: DoctorEvidence[];
  timeline: DoctorTimeline | null;
  changes: DoctorChanges | null;
  actions: DoctorAction[];
  missing_signals: DoctorMissingSignal[];
  /** Réponse brute de l'IA quand elle n'a pas pu être structurée. */
  raw_text: string | null;
  ai: DoctorAIInfo;
  user_role: CnpTier | 'admin';
}
