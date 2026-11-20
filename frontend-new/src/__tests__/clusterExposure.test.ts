import { describe, expect, it } from 'vitest';
import type { ClusterConnection } from '@/types';
import { clusterSupportsExposure, effectiveTargetCluster } from '@/utils/clusterUtils';
import { portForwardCommand } from '@/utils/appUrls';

function cluster(id: number, name: string, supports_public_exposure: boolean): ClusterConnection {
  return {
    id, name, endpoint: `https://${name}`, provider: 'other', kubeconfig_secret_ref: 'x',
    status: 'online', created_at: '2026-01-01T00:00:00Z', app_count: 0, supports_public_exposure,
  };
}

describe('clusterSupportsExposure', () => {
  it('follows the backend flag, not the cluster name', () => {
    expect(clusterSupportsExposure(cluster(1, 'cnp-aks', true))).toBe(true);
    // The old name heuristic (`!name.includes('k3s')`) wrongly allowed GKE.
    expect(clusterSupportsExposure(cluster(2, 'cnp-gke', false))).toBe(false);
    expect(clusterSupportsExposure(null)).toBe(false);
  });
});

describe('effectiveTargetCluster', () => {
  const clusters = [cluster(3, 'cnp-aks', true), cluster(2, 'cnp-k3s', false)];

  it('returns the selected cluster', () => {
    expect(effectiveTargetCluster(clusters, 3)?.name).toBe('cnp-aks');
  });

  it('falls back to the backend default: the lowest id', () => {
    expect(effectiveTargetCluster(clusters, null)?.name).toBe('cnp-k3s');
    expect(effectiveTargetCluster([], null)).toBeNull();
  });
});

describe('portForwardCommand', () => {
  it('targets the dev namespace and the app port, on a local port the dev realm allows', () => {
    expect(portForwardCommand('demo')).toBe('kubectl port-forward -n dev svc/demo 8000:8000');
    expect(portForwardCommand('demo', 3000)).toBe('kubectl port-forward -n dev svc/demo 8000:3000');
    expect(portForwardCommand(undefined)).toBe('kubectl port-forward -n dev svc/<slug> 8000:8000');
  });
});
