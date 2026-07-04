import { useQuery } from '@tanstack/react-query';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { finopsApi } from '@/api/finops';
import { TeamCostEntry } from '@/types';
import { useTheme } from '@/contexts/ThemeContext';
import { Skeleton } from '@/components/ui/skeleton';

function formatEur(value: number): string {
  if (value < 0.001) return '< €0.001';
  if (value < 0.01) return `€${value.toFixed(3)}`;
  return `€${value.toFixed(2)}`;
}

function truncate(name: string, max = 28): string {
  return name.length > max ? name.slice(0, max - 1) + '…' : name;
}

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ value: number; payload: { fullName: string } }>;
}

function CustomTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload?.length) return null;
  const value = payload[0].value;
  const name = payload[0].payload.fullName;
  return (
    <div className="rounded-lg border border-border bg-background shadow-md px-3 py-2 text-xs">
      <p className="font-medium text-foreground mb-1 truncate max-w-[200px]">{name}</p>
      <span className="font-mono text-foreground">{formatEur(value)}</span>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-40 text-center gap-2">
      <p className="text-sm text-muted-foreground">No cost data available.</p>
      <p className="text-xs text-muted-foreground">Apps need to be running to generate metrics.</p>
    </div>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center h-40 text-center gap-2">
      <p className="text-sm text-muted-foreground">Failed to load cost data.</p>
      <button onClick={onRetry} className="text-xs text-primary hover:underline">
        Retry
      </button>
    </div>
  );
}

export function FinopsCostByTeamChart() {
  const { theme } = useTheme();
  const isDark = theme === 'dark';

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['finops-cost-by-team'],
    queryFn: () => finopsApi.getCostByTeam(),
    staleTime: 60_000,
    retry: 1,
  });

  const textColor = isDark ? '#9ca3af' : '#6b7280';
  const gridColor = isDark ? '#374151' : '#e5e7eb';

  if (isLoading) {
    return (
      <div className="space-y-2 py-2">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-8 w-full rounded" />
        ))}
      </div>
    );
  }

  if (isError) return <ErrorState onRetry={() => refetch()} />;
  if (!data || data.length === 0) return <EmptyState />;

  const chartData = data.map((d: TeamCostEntry) => ({
    name: truncate(d.group_name),
    fullName: d.group_name,
    cost: d.cost_eur_month,
  }));

  const chartHeight = Math.max(160, chartData.length * 40 + 40);
  const longestName = Math.max(...chartData.map((d) => d.name.length));
  const yAxisWidth = Math.min(Math.max(longestName * 7, 100), 220);

  return (
    <ResponsiveContainer width="100%" height={chartHeight}>
      <BarChart
        data={chartData}
        layout="vertical"
        margin={{ top: 4, right: 32, left: 0, bottom: 4 }}
        barSize={18}
      >
        <CartesianGrid horizontal={false} strokeDasharray="3 3" stroke={gridColor} />
        <XAxis
          type="number"
          tick={{ fill: textColor, fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          tickFormatter={formatEur}
        />
        <YAxis
          type="category"
          dataKey="name"
          width={yAxisWidth}
          tick={{ fill: textColor, fontSize: 12 }}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          content={<CustomTooltip />}
          cursor={{ fill: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)' }}
        />
        <Bar dataKey="cost" radius={[0, 4, 4, 0]}>
          {chartData.map((_, i) => (
            <Cell key={i} fill="#007BA7" />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
