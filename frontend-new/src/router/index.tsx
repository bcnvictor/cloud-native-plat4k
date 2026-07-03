import { createBrowserRouter, Navigate } from 'react-router-dom';
import { RootLayout } from '@/layouts/RootLayout';
import { ProtectedRoute, AdminRoute, RootRedirect } from './guards';

import { Login } from '@/pages/Login';
import { OAuthCallback } from '@/pages/OAuthCallback';
import { GroupHome } from '@/pages/group/GroupHome';
import { GroupApps } from '@/pages/group/GroupApps';
import { GroupSettings } from '@/pages/group/GroupSettings';
import { AppDetailLayout } from '@/layouts/AppDetailLayout';
import { OverviewTab } from '@/pages/group/app/tabs/OverviewTab';
import { LogsTab } from '@/pages/group/app/tabs/LogsTab';
import { HistoryTab } from '@/pages/group/app/tabs/HistoryTab';
import { SettingsTab } from '@/pages/group/app/tabs/SettingsTab';
import { AssistantTab } from '@/pages/group/app/tabs/AssistantTab';
import { NewApp } from '@/pages/group/app/NewApp';
import { Clusters } from '@/pages/admin/Clusters';
import { FinOps } from '@/pages/admin/FinOps';
import { AdminApps } from '@/pages/admin/AdminApps';
import { AdminSettings } from '@/pages/admin/AdminSettings';
import { AdminUsers } from '@/pages/admin/AdminUsers';
import { AdminAudit } from '@/pages/admin/AdminAudit';
import { Profile } from '@/pages/Profile';
import { GroupMetrics } from '@/pages/group/GroupMetrics';

export const router = createBrowserRouter([
  { path: '/login', element: <Login /> },
  { path: '/oauth/callback', element: <OAuthCallback /> },

  {
    element: <ProtectedRoute />,
    children: [
      {
        element: <RootLayout />,
        children: [
          { path: '/groups/:slug', element: <GroupHome /> },
          { path: '/groups/:slug/apps', element: <GroupApps /> },
          { path: '/groups/:slug/apps/new', element: <NewApp /> },
          {
            path: '/groups/:slug/apps/:appSlug',
            element: <AppDetailLayout />,
            children: [
              { index: true, element: <OverviewTab /> },
              { path: 'logs', element: <LogsTab /> },
              { path: 'history', element: <HistoryTab /> },
              { path: 'settings', element: <SettingsTab /> },
              { path: 'assistant', element: <AssistantTab /> },
            ],
          },
          { path: '/groups/:slug/metrics', element: <GroupMetrics /> },
          { path: '/groups/:slug/settings', element: <GroupSettings /> },
        ],
      },
    ],
  },

  {
    element: <AdminRoute />,
    children: [
      {
        element: <RootLayout />,
        children: [
          { path: '/admin/clusters', element: <Clusters /> },
          { path: '/admin/finops', element: <FinOps /> },
          { path: '/admin/apps', element: <AdminApps /> },
          { path: '/admin/users', element: <AdminUsers /> },
          { path: '/admin/audit', element: <AdminAudit /> },
          { path: '/admin/settings', element: <AdminSettings /> },
        ],
      },
    ],
  },

  {
    element: <ProtectedRoute />,
    children: [
      {
        element: <RootLayout />,
        children: [
          { path: '/profile', element: <Profile /> },
        ],
      },
    ],
  },

  { path: '/', element: <RootRedirect /> },
  { path: '*', element: <Navigate to="/" replace /> },
]);
