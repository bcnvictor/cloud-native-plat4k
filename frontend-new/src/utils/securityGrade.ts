import type { SecurityGrade, SecuritySeverity } from '@/types';

export const SEVERITIES: SecuritySeverity[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'UNKNOWN'];

type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'muted';

export function gradeVariant(grade: SecurityGrade | null | undefined): BadgeVariant {
  if (!grade) return 'muted';
  if (grade === 'A' || grade === 'B') return 'success';
  if (grade === 'C') return 'warning';
  return 'danger';
}

export function severityVariant(sev: SecuritySeverity): BadgeVariant {
  switch (sev) {
    case 'CRITICAL':
    case 'HIGH':
      return 'danger';
    case 'MEDIUM':
      return 'warning';
    case 'LOW':
      return 'info';
    default:
      return 'muted';
  }
}
