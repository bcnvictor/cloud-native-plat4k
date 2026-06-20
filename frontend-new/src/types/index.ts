export type UserRole = 'admin' | 'dev' | 'viewer';
export type CnpTier = 'viewer' | 'developer' | 'maintainer' | 'owner';

export type ApplicationStatus = 'onboarding' | 'ready' | 'deployed';
export type DeploymentStatus = 'pending' | 'running' | 'succeeded' | 'failed';

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
  repo_url: string | null;
  owner: string;
  origin: AppOrigin | null;
  source_url: string | null;
  status: ApplicationStatus;
  framework?: string | null;
  gitlab_project_id?: number | null;
  owning_gitlab_group_id?: number | null;
  created_at: string;
  updated_at: string | null;
}

export interface Deployment {
  id: number;
  application_id: number;
  cluster_id: number;
  version: string;
  status: DeploymentStatus;
  deployed_at: string;
  created_at: string;
}

export interface DeploymentExtended extends Deployment {
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
  created_at: string;
}

export interface ClusterMetrics {
  nodesActive: number;
  cpuUsed: number;
  cpuTotal: number;
  ramUsedGi: number;
  ramTotalGi: number;
  k8sVersion: string;
  type: string;
  provider: string;
  icon: 'cloud' | 'server';
  podsActive: number;
  namespaces: Array<{ name: string; apps: number; pods: number }>;
}

export interface LogEntry {
  timestamp: string;
  level: 'INFO' | 'WARN' | 'ERROR' | 'DEBUG';
  message: string;
  pod?: string;
}

export interface MonitoringMetrics {
  apps: Array<{
    app_name: string;
    cpu_percent: number;
    ram_mb: number;
    cost_estimate: number;
  }>;
}

export interface EnvVar {
  key: string;
  value: string;
  masked: boolean;
}

export interface AppTemplate {
  id: string;
  name: string;
  description: string;
  framework: string;
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

export interface FinOpsData {
  period: string;
  totalCostUsd: number;
  azureCreditsTotal: number;
  azureCreditsUsed: number;
  azureCreditsRemainingDays: number;
  clusters: Array<{ name: string; provider: string; costUsd: number }>;
  groups: Array<{
    groupName: string;
    totalUsd: number;
    apps: Array<{ appName: string; costUsd: number }>;
  }>;
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
}
