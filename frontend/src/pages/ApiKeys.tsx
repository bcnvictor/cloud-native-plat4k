import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { authApi } from '@/api/auth';
import type { ApiKey } from '@/types';
import { Trash2, Plus, Copy, Check } from 'lucide-react';

export const ApiKeys = () => {
  const queryClient = useQueryClient();
  const [label, setLabel] = useState('');
  const [newKey, setNewKey] = useState<{ raw: string; label: string } | null>(null);
  const [copied, setCopied] = useState(false);

  const { data: keys, isLoading } = useQuery({
    queryKey: ['apikeys'],
    queryFn: () => authApi.getApiKeys(),
  }) as { data: ApiKey[] | undefined; isLoading: boolean };

  const createMutation = useMutation({
    mutationFn: (label: string) => authApi.createApiKey(label),
    onSuccess: (data) => {
      setNewKey({ raw: data.api_key, label: data.label });
      setLabel('');
      queryClient.invalidateQueries({ queryKey: ['apikeys'] });
    },
  });

  const revokeMutation = useMutation({
    mutationFn: (id: number) => authApi.revokeApiKey(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['apikeys'] });
    },
  });

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (label.trim()) {
      createMutation.mutate(label);
    }
  };

  const copyToClipboard = () => {
    if (newKey) {
      navigator.clipboard.writeText(newKey.raw);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  if (isLoading) return <div>Loading...</div>;

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-gray-900">API Keys</h1>
        <p className="mt-2 text-sm text-gray-700">Manage API keys for CLI access.</p>
      </div>

      <div className="bg-white shadow sm:rounded-lg mb-8 p-6">
        <h3 className="text-lg leading-6 font-medium text-gray-900">Create New Key</h3>
        <form className="mt-5 sm:flex sm:items-center" onSubmit={handleCreate}>
          <div className="w-full sm:max-w-xs">
            <label htmlFor="label" className="sr-only">Key Label</label>
            <input
              type="text"
              name="label"
              id="label"
              className="shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-gray-300 rounded-md"
              placeholder="e.g. My CLI Macbook"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            />
          </div>
          <button
            type="submit"
            disabled={!label.trim() || createMutation.isPending}
            className="mt-3 w-full inline-flex items-center justify-center px-4 py-2 border border-transparent shadow-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 sm:mt-0 sm:ml-3 sm:w-auto sm:text-sm disabled:opacity-50"
          >
            <Plus className="h-4 w-4 mr-2" />
            Generate
          </button>
        </form>

        {newKey && (
          <div className="mt-6 bg-yellow-50 border-l-4 border-yellow-400 p-4">
            <div className="flex">
              <div className="ml-3">
                <h3 className="text-sm font-medium text-yellow-800">
                  Save your new API key!
                </h3>
                <div className="mt-2 text-sm text-yellow-700">
                  <p>This key will only be shown once. Please copy it now.</p>
                </div>
                <div className="mt-4 flex items-center space-x-2">
                  <code className="px-3 py-2 bg-white border border-yellow-200 rounded text-sm font-mono flex-1">
                    {newKey.raw}
                  </code>
                  <button
                    onClick={copyToClipboard}
                    className="inline-flex items-center px-3 py-2 border border-transparent text-sm leading-4 font-medium rounded-md text-yellow-700 bg-yellow-100 hover:bg-yellow-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-yellow-500"
                  >
                    {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="bg-white shadow overflow-hidden sm:rounded-lg">
        <ul className="divide-y divide-gray-200">
          {keys?.filter((key) => !key.revoked).map((key) => (
            <li key={key.id}>
              <div className="px-4 py-4 flex items-center sm:px-6">
                <div className="min-w-0 flex-1 sm:flex sm:items-center sm:justify-between">
                  <div>
                    <h4 className="text-sm font-medium text-blue-600 truncate">{key.label}</h4>
                    <p className="mt-1 flex items-center text-sm text-gray-500">
                      Created on {new Date(key.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <div className="mt-4 flex-shrink-0 sm:mt-0 sm:ml-5">
                    <p className="text-sm text-gray-500">
                      Last used: {key.last_used_at ? new Date(key.last_used_at).toLocaleDateString() : 'Never'}
                    </p>
                  </div>
                </div>
                <div className="ml-5 flex-shrink-0">
                  <button
                    onClick={() => revokeMutation.mutate(key.id)}
                    className="p-2 text-red-600 hover:text-red-900 rounded-md hover:bg-red-50"
                    title="Revoke Key"
                  >
                    <Trash2 className="h-5 w-5" />
                  </button>
                </div>
              </div>
            </li>
          ))}
          {keys?.filter((key) => !key.revoked).length === 0 && (
            <li className="px-4 py-8 text-center text-gray-500">
              No active API keys found.
            </li>
          )}
        </ul>
      </div>
    </div>
  );
};
