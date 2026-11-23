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
