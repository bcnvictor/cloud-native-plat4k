import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { dependenciesApi, type DependencyFilters } from '@/api/dependencies';

export function useDependencySearch(filters: DependencyFilters) {
  return useQuery({
    queryKey: ['admin-dependencies', filters],
    queryFn: () => dependenciesApi.search(filters),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
    retry: 1,
  });
}

export function useCveSearch(cveId: string | null) {
  return useQuery({
    queryKey: ['admin-dependencies-by-cve', cveId],
    queryFn: () => dependenciesApi.searchByCve(cveId!),
    enabled: !!cveId,
    staleTime: 60_000,
    retry: false, // errors are meaningful (unknown CVE, OSV down): show them, let the admin retry
  });
}
