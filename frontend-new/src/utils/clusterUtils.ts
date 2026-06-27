import type { ClusterConnection } from '@/types';

/**
 * Returns true if the cluster has nginx-ingress configured and can expose apps on
 * cloud-native-plat4k.me subdomains.
 *
 * Currently only AKS satisfies this: its Terraform provisions nginx-ingress + the
 * wildcard DNS record. k3s clusters do not have nginx-ingress yet — expose must be
 * disabled for them at the UI level so the backend never writes an ingress that
 * would silently not resolve.
 *
 * Detection: k3s clusters are identified by "k3s" in their name (the canonical name
 * set at registration time). Update this predicate when k3s gains ingress support.
 */
export function clusterSupportsIngress(cluster: ClusterConnection): boolean {
  return !cluster.name.toLowerCase().includes('k3s');
}

/** Returns true for clusters running on private infra (non-managed, e.g. k3s on Oracle). */
export function isPrivateCluster(cluster: ClusterConnection): boolean {
  return cluster.name.toLowerCase().includes('k3s')
    || cluster.name.toLowerCase().includes('oracle')
    || cluster.name.toLowerCase().includes('priv');
}
