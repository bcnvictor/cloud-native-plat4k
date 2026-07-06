export type UserRole = 'admin' | 'dev' | 'viewer';
export type CnpTier = 'viewer' | 'developer' | 'maintainer' | 'owner';

export type ApplicationStatus = 'onboarding' | 'ready' | 'deployed' | 'degraded';
export type AppHealthStatus =
  | 'healthy'
  | 'deploying'
  | 'updating'
  | 'unhealthy'
  | 'stopped'
  | 'provisioning';

export type AppOrigin = 'scaffold' | 'onboard' | 'import';
export type DeployTrigger = 'on_commit' | 'on_tag';

export interface CnpJwtPayload {
  sub: string;
  role: UserRole;
}

export interface UserMe {
  id: number;
  email: string;
  role: UserRole;
  is_active: boolean;
  is_admin: boolean;
  gitlab_user_id: number | null;
  created_at: string;
}

export interface GroupMembership {
  gitlab_group_id: number;
  name: string;
  full_path: string;
  access_level: number;
  tier_cnp: CnpTier;
  status: 'active' | 'pending_invite' | 'left';
}

export interface AppMember {
  cnp_user_id: number | null;
  display_name: string | null;
  email?: string;
  access_level: number;
  tier_cnp: CnpTier;
  status: 'active' | 'pending_invite' | 'left';
}

export interface Application {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  repo_url: string | null;
  owner: string;
  origin: AppOrigin | null;
  source_url: string | null;
  last_known_status: ApplicationStatus;
  framework?: string | null;
  gitlab_project_id?: number | null;
  owning_gitlab_group_id?: number | null;
  expose?: boolean | null;
  target_cluster_id?: number | null;
  created_at: string;
  updated_at: string | null;
}

export interface ArgoEnvStatus {
  sync_status: string | null;
  health_status: string | null;
  image: string | null;
  last_sync_at: string | null;
  error: string | null;
}

export interface AppHistoryEntry {
  id: number;
  deployedAt: string;
  deployStartedAt?: string;
  revisions: string[];
  initiatedBy: { automated?: boolean; username?: string };
}

export interface AppHistory {
  dev: AppHistoryEntry[];
  prod: AppHistoryEntry[];
}

export interface AppRuntimeStatus {
  pods_running: number | null;
  pods_total: number | null;
  replicas_desired: number | null;
  replicas_ready: number | null;
  replicas_available: number | null;
  argocd_dev: ArgoEnvStatus | null;
  argocd_prod: ArgoEnvStatus | null;
  k8s_error: string | null;
  argocd_error: string | null;
}

export type ScaleStopReason = 'schedule' | 'manual';

export interface AppScaleStateItem {
  is_stopped: boolean;
  stop_reason: ScaleStopReason | null;
  stopped_at: string | null;
  resumed_at: string | null;
}

export interface AppScaleStateResponse {
  dev: AppScaleStateItem | null;
  prod: AppScaleStateItem | null;
}

export interface DeploymentExtended {
  commitHash: string;
  commitMessage: string;
  branch: string;
  duration: number | null;
  trigger: DeployTrigger | 'manual';
  author: string;
  imageTag: string;
  gitlabPipelineUrl: string | null;
  isCurrent: boolean;
}

export interface ClusterConnection {
  id: number;
  name: string;
  endpoint: string;
  kubeconfig_secret_ref: string;
  prometheus_url?: string | null;
  loki_url?: string | null;
  argocd_url?: string | null;
  status: 'online' | 'offline' | 'unknown';
  last_seen_at?: string;
  created_at: string;
  updated_at?: string;
}

export interface LogEntry {
  timestamp: string;
  level: 'INFO' | 'WARN' | 'ERROR' | 'DEBUG';
  message: string;
  pod?: string;
}

export interface AppCostEntry {
  app_name: string;
  cpu_cost_usd: number;
  ram_cost_usd: number;
  total_cost_usd: number;
}

export interface MetricPoint { t: number; v: number }

export interface MonitoringMetrics {
  apps: Array<{
    app_name: string;
    cpu_current: number;
    cpu_series: MetricPoint[];
    ram_current_mb: number;
    ram_series: MetricPoint[];
  }>;
}

export interface EnvVar {
  key: string;
  value: string;
  masked: boolean;
}

export interface EnvVarKeyStatus {
  key: string;
  is_set: boolean;
}

export interface EnvVarListResponse {
  env: string;
  keys: EnvVarKeyStatus[];
}

export interface MyAccessResponse {
  tier: CnpTier;
  is_admin: boolean;
}

export interface AppTemplate {
  name: string;
  path: string;
  web_url: string;
}

export interface GitLabProject {
  id: number;
  name: string;
  full_path: string;
  web_url: string;
}

export interface ActivityEvent {
  id: string;
  type: 'deploy_success' | 'deploy_failed' | 'provisioning' | 'replica_error' | 'member_added';
  appName?: string;
  memberName?: string;
  groupName?: string;
  timestamp: string;
}

export interface FinopsGrafanaUrls {
  total_cost_panel_url: string | null;
  top_apps_panel_url: string | null;
  trend_panel_url: string | null;
  dashboard_url: string | null;
}

export interface TeamCostEntry {
  group_id: string;
  group_name: string;
  cost_eur_month: number;
}

// Stepper form state
export interface Step1Data {
  origin: 'scaffold' | 'onboard';
  name: string;
  framework: string;
  repoUrl: string;
}

export interface ServiceConfig {
  database: { enabled: boolean; dbName: string; pgSize: '1Gi' | '5Gi' | '20Gi' };
  auth: { enabled: boolean };
  cache: { enabled: boolean };
}

export interface CiDeployConfig {
  trigger: DeployTrigger;
  envVars: EnvVar[];
  replicas: number;
  targetClusterId: number | null;
  advancedOpen: boolean;
  expose: boolean;
}

export interface ApiKey {
  id: number;
  label: string;
  key_prefix: string;
  created_at: string;
  last_used_at: string | null;
  is_active: boolean;
}

export interface AuditLog {
  id: number;
  user_id: number | null;
  user_email?: string | null;
  action: string;
  cloud?: string | null;
  resource_id?: string | null;
  app_id?: number | null;
  app_name?: string | null;
  ip_address?: string | null;
  extra?: Record<string, unknown> | null;
  timestamp: string;
}

export type NotificationSeverity = 'info' | 'warning' | 'critical';
export type NotificationState = 'new' | 'read' | 'acknowledged';

export interface NotificationEvent {
  id: number;
  type: string;
  severity: NotificationSeverity;
  source: string;
  app_id: number | null;
  payload: Record<string, unknown>;
  dedup_key: string;
  created_at: string;
}

export interface Notification {
  id: number;
  event: NotificationEvent;
  state: NotificationState;
  read_at: string | null;
  created_at: string;
}

export interface NotificationPreference {
  category: string;
  enabled: boolean;
}

export interface AdminUser {
  id: number;
  email: string;
  role: UserRole;
  is_active: boolean;
  is_admin: boolean;
  gitlab_user_id: number | null;
  created_at: string;
}

// ── AI Assistant ──────────────────────────────────────────────────────────────

export type AIContextMode = 'metadata_only' | 'metadata_and_code';

export interface AIAppSettings {
  app_id: number;
  ai_enabled: boolean;
  ai_context_mode: AIContextMode;
  ai_security_scan_enabled: boolean;
  ai_security_summary_enabled: boolean;
  code_access_warning_accepted_by_user_id: number | null;
  code_access_warning_accepted_at: string | null;
  updated_by_user_id: number | null;
  updated_at: string;
}

export interface AIAppSettingsPatch {
  ai_enabled?: boolean;
  ai_context_mode?: AIContextMode;
  ai_security_scan_enabled?: boolean;
  ai_security_summary_enabled?: boolean;
  accept_code_access_warning?: boolean;
}

export interface ChatPayload {
  message: string;
  mode?: string;
  agent?: string;
  requested_context_mode?: AIContextMode;
  conversation_id?: string;
}

export interface DocCitation {
  type: string;
  path?: string;
  heading?: string | null;
  ref?: string;
}

export interface AIGlobalSettings {
  assistant_enabled: boolean;
  graphical_bot_enabled: boolean;
  platform_data_access_enabled: boolean;
  app_data_access_enabled: boolean;
  allowed_app_ids: number[];
  provider: string;
  model: string;
  api_key_set: boolean;
  source: string; // "db" | "env"
  updated_by_user_id?: number | null;
  updated_at?: string | null;
}

export interface AIGlobalSettingsPatch {
  assistant_enabled?: boolean;
  graphical_bot_enabled?: boolean;
  platform_data_access_enabled?: boolean;
  app_data_access_enabled?: boolean;
  allowed_app_ids?: number[];
  provider?: string;
  model?: string;
  api_key?: string; // "" clears the stored key
}

export interface AIUISettings {
  assistant_enabled: boolean;
  graphical_bot_enabled: boolean;
}

export interface ChatResponse {
  conversation_id: string;
  answer: string;
  citations: unknown[];
  used_tools: string[];
  usage: {
    input_tokens: number;
    output_tokens: number;
    estimated_cost_usd: number;
  };
}
