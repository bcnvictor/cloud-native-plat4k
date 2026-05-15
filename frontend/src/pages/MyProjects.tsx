import { useState } from 'react';
import { FolderGit2, GitBranch, Plus, Download } from 'lucide-react';
import { clsx } from 'clsx';
import { useQuery } from '@tanstack/react-query';
import { gitlabApi, GitLabProject } from '@/api/gitlab';

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

const ACTIVITY_BADGE: Record<'active' | 'stale', string> = {
  active: 'bg-green-100 text-green-800',
  stale: 'bg-gray-100 text-gray-800',
};

function getActivityStatus(lastActivity?: string | null) {
  if (!lastActivity) return 'stale' as const;
  const date = new Date(lastActivity);
  const diffDays = (Date.now() - date.getTime()) / (1000 * 60 * 60 * 24);
  return diffDays <= 30 ? 'active' : 'stale';
}

export const MyProjects = () => {
  const [toast, setToast] = useState<string | null>(null);
  const { data: projects = [], isLoading, isError } = useQuery({
    queryKey: ['gitlab-projects'],
    queryFn: () => gitlabApi.listProjects(),
  });

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

  const handleComingSoon = () => showToast('Coming soon');

  const ActionButtons = () => (
    <div className="flex items-center gap-3">
      <button
        onClick={handleComingSoon}
        className="inline-flex items-center gap-2 rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50"
      >
        <Download className="h-4 w-4" />
        Import existing repo
      </button>
      <button
        onClick={handleComingSoon}
        className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700"
      >
        <Plus className="h-4 w-4" />
        Scaffold new project
      </button>
    </div>
  );

  if (isLoading) {
    return <div>Loading GitLab projects...</div>;
  }

  if (isError) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-600">
        Unable to load GitLab projects. Ensure GitLab is connected.
      </div>
    );
  }

  return (
    <>
      <div className="mb-8 flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900">My Projects</h1>
        <ActionButtons />
      </div>

      {projects.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-200 bg-white py-20 text-center">
          <FolderGit2 className="mb-4 h-12 w-12 text-gray-300" />
          <h3 className="mb-1 text-sm font-semibold text-gray-900">No projects yet</h3>
          <p className="mb-6 text-sm text-gray-500">No GitLab repositories found.</p>
          <ActionButtons />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((project: GitLabProject) => {
            const activity = getActivityStatus(project.last_activity_at);
            return (
            <div
              key={project.id}
              className="flex flex-col overflow-hidden rounded-lg bg-white shadow"
            >
              <div className="flex flex-1 flex-col p-5">
                <div className="mb-3 flex items-start justify-between gap-2">
                  <h3 className="truncate text-sm font-semibold text-gray-900">
                    {project.name}
                  </h3>
                  <span
                    className={clsx(
                      'flex-shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium capitalize',
                      ACTIVITY_BADGE[activity]
                    )}
                  >
                    {activity}
                  </span>
                </div>

                <div className="mb-4 flex items-center gap-1.5 text-xs text-gray-500">
                  <GitBranch className="h-3.5 w-3.5 flex-shrink-0 text-gray-400" />
                  <span className="truncate">{project.path_with_namespace}</span>
                </div>

                <div className="mt-auto flex items-center justify-between">
                  <span className="text-xs text-gray-400">
                    {project.last_activity_at ? formatDate(project.last_activity_at) : 'No activity'}
                  </span>
                  <a
                    href={project.web_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs font-medium text-blue-600 hover:text-blue-500"
                  >
                    Open
                  </a>
                </div>
              </div>

              <div className="border-t border-gray-100 px-5 py-3">
                <button className="text-sm font-medium text-blue-600 hover:text-blue-500">
                  View details
                </button>
              </div>
            </div>
          );
          })}
        </div>
      )}

      {toast && (
        <div className="fixed bottom-6 right-6 z-50 rounded-lg bg-gray-900 px-4 py-3 text-sm text-white shadow-lg">
          {toast}
        </div>
      )}
    </>
  );
};
