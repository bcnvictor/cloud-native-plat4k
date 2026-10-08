import type { ClusterTestResult } from '@/types';

export function TestResultLine({ result }: { result: ClusterTestResult }) {
  return result.reachable ? (
    <p className="text-xs text-success-text">
      ✓ Reachable · {result.latency_ms} ms · {result.namespace_count} namespaces
    </p>
  ) : (
    <p className="text-xs text-danger-text break-words">✕ Unreachable · {result.error ?? 'unknown error'}</p>
  );
}
