export type CloudType = 'aws' | 'gcp' | 'openstack';
export type ResourceType = 'vm' | 'storage' | 'network';
export type ResourceStatus = 'pending' | 'running' | 'stopped' | 'terminated' | 'error';
export type UserRole = 'admin' | 'dev' | 'viewer';

export interface CnpJwtPayload {
  sub: string;
  role: UserRole;
}

export type ApplicationStatus = 'onboarding' | 'ready' | 'deployed';
export type DeploymentStatus = 'pending' | 'running' | 'succeeded' | 'failed';
export type CnpTier = 'viewer' | 'developer' | 'maintainer' | 'owner';

export interface AppMember {
  cnp_user_id: number | null;
  display_name: string | null;
  access_level: number;
  tier_cnp: CnpTier;
  status: 'active' | 'pending_invite' | 'left';
}

export interface MyAccess {
  tier: CnpTier;
  is_admin: boolean;
}

export interface GroupMembership {
  gitlab_group_id: number;
  name: string;
  full_path: string;
  access_level: number;
  tier_cnp: CnpTier;
  status: 'active' | 'pending_invite' | 'left';
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

export interface Application {
  id: number;
  name: string;
  repo_url: string | null;
  owner: string;
  origin: string | null;
  source_url: string | null;
  status: ApplicationStatus;
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

export interface User {
  id: number;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface Resource {
  id: number;
  cloud: CloudType;
  type: ResourceType;
  external_id: string;
  name: string;
  status: ResourceStatus;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface Credential {
  id: number;
  cloud: CloudType;
  created_at: string;
}

export interface ApiKey {
  id: number;
  label: string;
  last_used_at: string | null;
  created_at: string;
  revoked: boolean;
}

export interface AuditLog {
  id: number;
  user_id: number;
  action: string;
  resource_id: number | null;
  cloud: CloudType | null;
  timestamp: string;
  ip_address: string;
}
