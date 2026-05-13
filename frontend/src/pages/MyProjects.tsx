import { useState } from 'react';
import { FolderGit2, GitBranch, Plus, Download } from 'lucide-react';
import { clsx } from 'clsx';

type Origin = 'scaffolded' | 'imported';
type ProjectStatus = 'deployed' | 'pending' | 'error';

interface Project {
  id: string;
  name: string;
  origin: Origin;
  repo: string;
  status: ProjectStatus;
  createdAt: string;
}

const MOCK_PROJECTS: Project[] = [
  {
    id: '1',
    name: 'api-gateway-service',
    origin: 'scaffolded',
    repo: 'gitlab.company.com/team-backend/api-gateway-service',
    status: 'deployed',
    createdAt: '2024-03-15',
  },
  {
    id: '2',
    name: 'frontend-dashboard',
    origin: 'scaffolded',
    repo: 'gitlab.company.com/team-frontend/frontend-dashboard',
    status: 'pending',
    createdAt: '2024-04-02',
  },
  {
    id: '3',
    name: 'legacy-auth-service',
    origin: 'imported',
    repo: 'gitlab.company.com/team-platform/legacy-auth-service',
    status: 'error',
    createdAt: '2024-02-20',
  },
  {
    id: '4',
    name: 'data-pipeline-worker',
    origin: 'imported',
    repo: 'gitlab.company.com/team-data/data-pipeline-worker',
    status: 'deployed',
    createdAt: '2024-04-18',
  },
];

const ORIGIN_BADGE: Record<Origin, string> = {
  scaffolded: 'bg-green-100 text-green-800',
  imported: 'bg-indigo-100 text-indigo-800',
};

const STATUS_BADGE: Record<ProjectStatus, string> = {
  deployed: 'bg-green-100 text-green-800',
  pending: 'bg-yellow-100 text-yellow-800',
  error: 'bg-red-100 text-red-800',
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export const MyProjects = () => {
  const [toast, setToast] = useState<string | null>(null);
  const projects = MOCK_PROJECTS;

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
          <p className="mb-6 text-sm text-gray-500">
            Get started by scaffolding a new project or importing an existing repository.
          </p>
          <ActionButtons />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
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
                      ORIGIN_BADGE[project.origin]
                    )}
                  >
                    {project.origin}
                  </span>
                </div>

                <div className="mb-4 flex items-center gap-1.5 text-xs text-gray-500">
                  <GitBranch className="h-3.5 w-3.5 flex-shrink-0 text-gray-400" />
                  <span className="truncate">{project.repo}</span>
                </div>

                <div className="mt-auto flex items-center justify-between">
                  <span
                    className={clsx(
                      'rounded-full px-2.5 py-0.5 text-xs font-medium capitalize',
                      STATUS_BADGE[project.status]
                    )}
                  >
                    {project.status}
                  </span>
                  <span className="text-xs text-gray-400">{formatDate(project.createdAt)}</span>
                </div>
              </div>

              <div className="border-t border-gray-100 px-5 py-3">
                <button className="text-sm font-medium text-blue-600 hover:text-blue-500">
                  View details
                </button>
              </div>
            </div>
          ))}
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
