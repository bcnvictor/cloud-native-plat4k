import { createBrowserRouter } from 'react-router-dom';
import { ProtectedRoute } from './ProtectedRoute';
import { Layout } from '@/components/Layout';
import { Login } from '@/pages/Login';
import { OAuthCallback } from '@/pages/OAuthCallback';
import { Dashboard } from '@/pages/Dashboard';
import { Resources } from '@/pages/Resources';
import { ResourceDetail } from '@/pages/ResourceDetail';
import { Credentials } from '@/pages/Credentials';
import { ApiKeys } from '@/pages/ApiKeys';
import { Users } from '@/pages/admin/Users';
import { Audit } from '@/pages/admin/Audit';
import { MyProjects } from '@/pages/MyProjects';

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <Login />,
  },
  {
    path: '/oauth/callback',
    element: <OAuthCallback />,
  },
  {
    path: '/',
    element: <ProtectedRoute />,
    children: [
      {
        element: <Layout />,
        children: [
          { index: true, element: <Dashboard /> },
          { path: 'dashboard', element: <Dashboard /> },
          { path: 'resources', element: <Resources /> },
          { path: 'resources/:id', element: <ResourceDetail /> },
          { path: 'credentials', element: <Credentials /> },
          { path: 'apikeys', element: <ApiKeys /> },
          { path: 'projects', element: <MyProjects /> },
        ],
      },
    ],
  },
  {
    path: '/admin',
    element: <ProtectedRoute requiredRole="admin" />,
    children: [
      {
        element: <Layout />,
        children: [
          { path: 'users', element: <Users /> },
          { path: 'audit', element: <Audit /> },
        ],
      },
    ],
  },
]);
