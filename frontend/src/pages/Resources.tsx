import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { resourcesApi } from '@/api/resources';
import { StatusBadge } from '@/components/StatusBadge';
import { ConfirmModal } from '@/components/ConfirmModal';
import { CloudType, ResourceType } from '@/types';
import { Trash2, Plus } from 'lucide-react';

export const Resources = () => {
  const [filterCloud, setFilterCloud] = useState<CloudType | ''>('');
  const [filterType, setFilterType] = useState<ResourceType | ''>('');
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [selectedResource, setSelectedResource] = useState<number | null>(null);

  const queryClient = useQueryClient();

  const { data: resources, isLoading } = useQuery({
    queryKey: ['resources', filterCloud, filterType],
    queryFn: () => resourcesApi.list({
      cloud: filterCloud || undefined,
      type: filterType || undefined
    }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => resourcesApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['resources'] });
      setDeleteModalOpen(false);
    },
  });

  const handleDeleteClick = (id: number) => {
    setSelectedResource(id);
    setDeleteModalOpen(true);
  };

  if (isLoading) return <div>Loading resources...</div>;

  return (
    <div>
      <div className="sm:flex sm:items-center sm:justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Resources</h1>
          <p className="mt-2 text-sm text-gray-700">A list of all cloud resources in your account.</p>
        </div>
        <div className="mt-4 sm:mt-0 flex gap-4">
          <select
            value={filterCloud}
            onChange={(e) => setFilterCloud(e.target.value as CloudType)}
            className="block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
          >
            <option value="">All Clouds</option>
            <option value="aws">AWS</option>
            <option value="gcp">GCP</option>
            <option value="openstack">OpenStack</option>
          </select>
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value as ResourceType)}
            className="block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
          >
            <option value="">All Types</option>
            <option value="vm">VM</option>
            <option value="storage">Storage</option>
            <option value="network">Network</option>
          </select>
          <button className="inline-flex items-center justify-center rounded-md border border-transparent bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 sm:w-auto">
            <Plus className="h-4 w-4 mr-2" />
            Create
          </button>
        </div>
      </div>

      <div className="mt-8 flex flex-col">
        <div className="-my-2 -mx-4 overflow-x-auto sm:-mx-6 lg:-mx-8">
          <div className="inline-block min-w-full py-2 align-middle md:px-6 lg:px-8">
            <div className="overflow-hidden shadow ring-1 ring-black ring-opacity-5 md:rounded-lg">
              <table className="min-w-full divide-y divide-gray-300">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-3 py-3.5 text-left text-sm font-semibold text-gray-900">Name</th>
                    <th className="px-3 py-3.5 text-left text-sm font-semibold text-gray-900">Cloud</th>
                    <th className="px-3 py-3.5 text-left text-sm font-semibold text-gray-900">Type</th>
                    <th className="px-3 py-3.5 text-left text-sm font-semibold text-gray-900">Status</th>
                    <th className="px-3 py-3.5 text-left text-sm font-semibold text-gray-900">External ID</th>
                    <th className="relative py-3.5 pl-3 pr-4 sm:pr-6">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 bg-white">
                  {resources?.map((resource) => (
                    <tr key={resource.id}>
                      <td className="whitespace-nowrap px-3 py-4 text-sm font-medium text-gray-900">{resource.name}</td>
                      <td className="whitespace-nowrap px-3 py-4 text-sm text-gray-500 uppercase">{resource.cloud}</td>
                      <td className="whitespace-nowrap px-3 py-4 text-sm text-gray-500 capitalize">{resource.type}</td>
                      <td className="whitespace-nowrap px-3 py-4 text-sm text-gray-500">
                        <StatusBadge status={resource.status} />
                      </td>
                      <td className="whitespace-nowrap px-3 py-4 text-sm text-gray-500 font-mono text-xs">{resource.external_id}</td>
                      <td className="relative whitespace-nowrap py-4 pl-3 pr-4 text-right text-sm font-medium sm:pr-6">
                        <button
                          onClick={() => handleDeleteClick(resource.id)}
                          className="text-red-600 hover:text-red-900"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                  {resources?.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-3 py-4 text-center text-sm text-gray-500">
                        No resources found.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      <ConfirmModal
        isOpen={deleteModalOpen}
        title="Delete Resource"
        message="Are you sure you want to delete this resource? This action cannot be undone and will destroy the underlying cloud infrastructure."
        onConfirm={() => selectedResource && deleteMutation.mutate(selectedResource)}
        onCancel={() => setDeleteModalOpen(false)}
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
};
