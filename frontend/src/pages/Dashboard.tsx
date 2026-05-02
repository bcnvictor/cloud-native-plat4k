import { useQuery } from '@tanstack/react-query';
import { resourcesApi } from '@/api/resources';
import { Activity, Server, HardDrive, Network } from 'lucide-react';

export const Dashboard = () => {
  const { data: resources, isLoading } = useQuery({
    queryKey: ['resources'],
    queryFn: () => resourcesApi.list(),
  });

  if (isLoading) return <div>Loading dashboard...</div>;

  const stats = {
    total: resources?.length || 0,
    vms: resources?.filter((r) => r.type === 'vm').length || 0,
    storage: resources?.filter((r) => r.type === 'storage').length || 0,
    networks: resources?.filter((r) => r.type === 'network').length || 0,
    running: resources?.filter((r) => r.status === 'running').length || 0,
  };

  const cards = [
    { name: 'Total Resources', value: stats.total, icon: Activity, color: 'text-blue-600' },
    { name: 'Virtual Machines', value: stats.vms, icon: Server, color: 'text-green-600' },
    { name: 'Storage Volumes', value: stats.storage, icon: HardDrive, color: 'text-purple-600' },
    { name: 'Networks', value: stats.networks, icon: Network, color: 'text-orange-600' },
  ];

  return (
    <div>
      <h1 className="text-2xl font-semibold text-gray-900 mb-6">Dashboard</h1>

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((card) => {
          const Icon = card.icon;
          return (
            <div key={card.name} className="bg-white overflow-hidden shadow rounded-lg">
              <div className="p-5">
                <div className="flex items-center">
                  <div className="flex-shrink-0">
                    <Icon className={`h-6 w-6 ${card.color}`} />
                  </div>
                  <div className="ml-5 w-0 flex-1">
                    <dl>
                      <dt className="text-sm font-medium text-gray-500 truncate">{card.name}</dt>
                      <dd className="text-lg font-medium text-gray-900">{card.value}</dd>
                    </dl>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-8">
        <h2 className="text-lg font-medium text-gray-900 mb-4">System Status</h2>
        <div className="bg-white shadow rounded-lg p-6">
          <p className="text-sm text-gray-500">
            {stats.running} resources currently running.
          </p>
        </div>
      </div>
    </div>
  );
};
