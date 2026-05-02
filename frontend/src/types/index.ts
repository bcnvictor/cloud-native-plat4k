export type CloudType = 'aws' | 'gcp' | 'openstack';
export type ResourceType = 'vm' | 'storage' | 'network';
export type ResourceStatus = 'pending' | 'running' | 'stopped' | 'terminated' | 'error';
export type UserRole = 'admin' | 'viewer';

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
  metadata: Record<string, any>;
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
