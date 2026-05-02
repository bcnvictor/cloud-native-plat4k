import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { credentialsApi } from '@/api/credentials';
import { CloudType } from '@/types';
import { Trash2, Plus, Key } from 'lucide-react';

export const Credentials = () => {
  const queryClient = useQueryClient();
  const [isAdding, setIsAdding] = useState(false);
  const [cloud, setCloud] = useState<CloudType>('aws');
  const [creds, setCreds] = useState('');

  const { data: credentials, isLoading } = useQuery({
    queryKey: ['credentials'],
    queryFn: () => credentialsApi.list(),
  });

  const addMutation = useMutation({
    mutationFn: (data: { cloud: CloudType; credentials: Record<string, string> }) =>
      credentialsApi.add(data.cloud, data.credentials),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['credentials'] });
      setIsAdding(false);
      setCreds('');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => credentialsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['credentials'] });
    },
  });

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const parsedCreds = JSON.parse(creds);
      addMutation.mutate({ cloud, credentials: parsedCreds });
    } catch (err) {
      alert('Invalid JSON format for credentials');
    }
  };

  if (isLoading) return <div>Loading...</div>;

  return (
    <div>
      <div className="sm:flex sm:items-center sm:justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Cloud Credentials</h1>
          <p className="mt-2 text-sm text-gray-700">Manage your access to AWS, GCP, and OpenStack.</p>
        </div>
        <div className="mt-4 sm:mt-0">
          <button
            onClick={() => setIsAdding(!isAdding)}
            className="inline-flex items-center justify-center rounded-md border border-transparent bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 sm:w-auto"
          >
            <Plus className="h-4 w-4 mr-2" />
            Add Credentials
          </button>
        </div>
      </div>

      {isAdding && (
        <div className="bg-white shadow sm:rounded-lg mb-8 p-6">
          <h3 className="text-lg leading-6 font-medium text-gray-900">New Credentials</h3>
          <form className="mt-5 space-y-4" onSubmit={handleAdd}>
            <div>
              <label className="block text-sm font-medium text-gray-700">Cloud Provider</label>
              <select
                value={cloud}
                onChange={(e) => setCloud(e.target.value as CloudType)}
                className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md"
              >
                <option value="aws">AWS</option>
                <option value="gcp">GCP</option>
                <option value="openstack">OpenStack</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Credentials (JSON format)</label>
              <textarea
                rows={4}
                value={creds}
                onChange={(e) => setCreds(e.target.value)}
                placeholder='{"aws_access_key_id": "...", "aws_secret_access_key": "..."}'
                className="mt-1 block w-full shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm border border-gray-300 rounded-md font-mono"
              />
            </div>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setIsAdding(false)}
                className="bg-white py-2 px-4 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={addMutation.isPending}
                className="inline-flex justify-center py-2 px-4 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
              >
                Save
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="bg-white shadow overflow-hidden sm:rounded-md">
        <ul className="divide-y divide-gray-200">
          {credentials?.map((cred) => (
            <li key={cred.id}>
              <div className="px-4 py-4 flex items-center sm:px-6">
                <div className="min-w-0 flex-1 sm:flex sm:items-center sm:justify-between">
                  <div className="flex items-center">
                    <div className="flex-shrink-0">
                      <Key className="h-6 w-6 text-gray-400" />
                    </div>
                    <div className="ml-4 flex-1 px-4">
                      <h4 className="text-lg font-bold text-blue-600 uppercase">
                        {cred.cloud}
                      </h4>
                      <p className="mt-1 flex items-center text-sm text-gray-500">
                        Added on {new Date(cred.created_at).toLocaleDateString()}
                      </p>
                    </div>
                  </div>
                </div>
                <div className="ml-5 flex-shrink-0">
                  <button
                    onClick={() => deleteMutation.mutate(cred.id)}
                    className="p-2 text-red-600 hover:text-red-900 rounded-md hover:bg-red-50"
                  >
                    <Trash2 className="h-5 w-5" />
                  </button>
                </div>
              </div>
            </li>
          ))}
          {credentials?.length === 0 && (
            <li className="px-4 py-8 text-center text-gray-500">
              No credentials configured.
            </li>
          )}
        </ul>
      </div>
    </div>
  );
};
