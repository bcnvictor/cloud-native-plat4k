import type { ClusterConnection, ClusterProvider } from '@/types';

export const PROVIDER_LABELS: Record<ClusterProvider, string> = {
  azure: 'Azure',
  aws: 'AWS',
  gcp: 'GCP',
  openstack: 'OpenStack',
  oracle: 'Oracle Cloud',
  other: 'Other',
};

/**
 * Whether apps on this cluster can be exposed on cloud-native-plat4k.me subdomains,
 * i.e. the public DNS reaches its ingress. Decided by the backend
 * (PUBLIC_EXPOSURE_CLUSTERS), which refuses expose=true anywhere else.
 */
export function clusterSupportsExposure(cluster: ClusterConnection | null | undefined): boolean {
  return cluster?.supports_public_exposure === true;
}

/**
 * The cluster an app lands on: the selected one, else the backend's default (the
 * first registered cluster, lowest id — AppService._resolve_target_cluster_id).
 */
export function effectiveTargetCluster(
  clusters: readonly ClusterConnection[],
  targetClusterId: number | null | undefined
): ClusterConnection | null {
  if (targetClusterId != null) return clusters.find((c) => c.id === targetClusterId) ?? null;
  return clusters.reduce<ClusterConnection | null>((first, c) => (first === null || c.id < first.id ? c : first), null);
}

/** Returns true for clusters running on private infra (non-managed, e.g. k3s on Oracle). */
export function isPrivateCluster(cluster: ClusterConnection): boolean {
  return cluster.name.toLowerCase().includes('k3s')
    || cluster.name.toLowerCase().includes('oracle')
    || cluster.name.toLowerCase().includes('priv');
}
