import { Navigate, Outlet } from 'react-router-dom';
import { useAuthStore } from '@/store/auth';
import { UserRole } from '@/types';

interface ProtectedRouteProps {
  requiredRole?: UserRole;
}

export const ProtectedRoute = ({ requiredRole }: ProtectedRouteProps) => {
  const { token, user } = useAuthStore();

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  if (requiredRole && user?.role !== 'admin' && user?.role !== requiredRole) {
    return <Navigate to="/dashboard" replace />;
  }

  return <Outlet />;
};
