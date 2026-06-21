import { Navigate, Outlet } from 'react-router-dom';
import { useAuthStore } from '@/store/auth';
import { useQuery } from '@tanstack/react-query';
import { groupsApi } from '@/api/groups';
import { Spinner } from '@/components/ui/Spinner';

export function ProtectedRoute() {
  const { token } = useAuthStore();
  if (!token) return <Navigate to="/login" replace />;
  return <Outlet />;
}

export function AdminRoute() {
  const { token, user } = useAuthStore();
  const { data: groups = [], isLoading } = useQuery({
    queryKey: ['my-groups'],
    queryFn: groupsApi.getMyGroups,
    enabled: !!token,
    staleTime: 5 * 60 * 1000,
  });

  if (!token) return <Navigate to="/login" replace />;
  if (!user?.is_admin) {
    const firstSlug = groups[0] ? groupsApi.getSlug(groups[0]) : null;
    if (isLoading) {
      return (
        <div className="flex items-center justify-center h-screen">
          <Spinner size="lg" />
        </div>
      );
    }
    return <Navigate to={firstSlug ? `/groups/${firstSlug}` : '/login'} replace />;
  }
  return <Outlet />;
}

export function RootRedirect() {
  const { token, user } = useAuthStore();
  const { data: groups = [], isLoading } = useQuery({
    queryKey: ['my-groups'],
    queryFn: groupsApi.getMyGroups,
    enabled: !!token,
    staleTime: 5 * 60 * 1000,
  });

  if (!token) return <Navigate to="/login" replace />;
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Spinner size="lg" />
      </div>
    );
  }

  const firstSlug = groups[0] ? groupsApi.getSlug(groups[0]) : null;
  if (firstSlug) return <Navigate to={`/groups/${firstSlug}`} replace />;
  if (user?.is_admin) return <Navigate to="/admin/clusters" replace />;
  return <Navigate to="/login" replace />;
}
