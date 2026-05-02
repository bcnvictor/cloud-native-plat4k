import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { resourcesApi } from '@/api/resources';
import { StatusBadge } from '@/components/StatusBadge';
import { ArrowLeft, Server, Activity, Database, Key } from 'lucide-react';

export const ResourceDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();

  const { data: resource, isLoading, isError } = useQuery({
    queryKey: ['resource', id],
    queryFn: () => resourcesApi.get(Number(id)),
    enabled: !!id,
  });

  if (isLoading) return <div>Loading resource details...</div>;
  if (isError || !resource) return <div className="text-red-500">Failed to load resource details.</div>;

  return (
    <div>
      <button
        onClick={() => navigate('/resources')}
        className="flex items-center text-sm text-gray-500 hover:text-gray-700 mb-6"
      >
        <ArrowLeft className="w-4 h-4 mr-1" />
        Back to Resources
      </button>

      <div className="bg-white shadow overflow-hidden sm:rounded-lg">
        <div className="px-4 py-5 sm:px-6 flex justify-between items-center">
          <div>
            <h3 className="text-lg leading-6 font-medium text-gray-900 flex items-center gap-2">
              <Server className="h-5 w-5 text-gray-400" />
              {resource.name}
            </h3>
            <p className="mt-1 max-w-2xl text-sm text-gray-500">
              Details and configuration.
            </p>
          </div>
          <StatusBadge status={resource.status} />
        </div>
        <div className="border-t border-gray-200 px-4 py-5 sm:p-0">
          <dl className="sm:divide-y sm:divide-gray-200">
            <div className="py-4 sm:py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
              <dt className="text-sm font-medium text-gray-500 flex items-center gap-2">
                <Activity className="w-4 h-4" />
                Cloud Provider
              </dt>
              <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2 uppercase">
                {resource.cloud}
              </dd>
            </div>
            <div className="py-4 sm:py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
              <dt className="text-sm font-medium text-gray-500 flex items-center gap-2">
                <Database className="w-4 h-4" />
                Resource Type
              </dt>
              <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2 capitalize">
                {resource.type}
              </dd>
            </div>
            <div className="py-4 sm:py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
              <dt className="text-sm font-medium text-gray-500 flex items-center gap-2">
                <Key className="w-4 h-4" />
                External ID
              </dt>
              <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2 font-mono bg-gray-50 p-2 rounded">
                {resource.external_id}
              </dd>
            </div>
            <div className="py-4 sm:py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
              <dt className="text-sm font-medium text-gray-500">Created At</dt>
              <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">
                {new Date(resource.created_at).toLocaleString()}
              </dd>
            </div>
            <div className="py-4 sm:py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
              <dt className="text-sm font-medium text-gray-500">Metadata</dt>
              <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">
                <pre className="bg-gray-50 p-4 rounded-md overflow-x-auto">
                  {JSON.stringify(resource.metadata, null, 2)}
                </pre>
              </dd>
            </div>
          </dl>
        </div>
      </div>
    </div>
  );
};
