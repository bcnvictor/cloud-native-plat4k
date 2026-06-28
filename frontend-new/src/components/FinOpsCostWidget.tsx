import { useQuery } from '@tanstack/react-query';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { monitoringApi } from '@/api/monitoring';
import { AppCostEntry } from '@/types';
import { useTheme } from '@/contexts/ThemeContext';
import { Skeleton } from '@/components/ui/skeleton';

interface Props {
  groupId: number;
}

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
  payload?: Array<{ name: string; value: number; color: string }>;
  label?: string;
}

function CustomTooltip({ active, payload, label }: TooltipProps) {
  if (!active || !payload?.length) return null;
  const total = payload.reduce((s, p) => s + p.value, 0);
  return (
    <div className="rounded-lg border border-border bg-background shadow-md px-3 py-2 text-xs">
      <p className="font-medium text-foreground mb-1.5 truncate max-w-[200px]">{label}</p>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <span className="w-2 h-2 rounded-full shrink-0" style={{ background: p.color }} />
            {p.name}
          </span>
          <span className="font-mono text-foreground">{formatEur(p.value)}</span>
        </div>
      ))}
      <div className="flex items-center justify-between gap-4 mt-1.5 pt-1.5 border-t border-border">
        <span className="text-muted-foreground">Total</span>
        <span className="font-mono font-semibold text-foreground">{formatEur(total)}</span>
      </div>
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

export function FinOpsCostWidget({ groupId }: Props) {
  const { theme } = useTheme();
  const isDark = theme === 'dark';

  const { data, isLoading, isError } = useQuery({
    queryKey: ['group-cost', groupId],
    queryFn: () => monitoringApi.getCostByGroup(groupId),
    staleTime: 60_000,
    retry: 1,
  });

  const textColor  = isDark ? '#9ca3af' : '#6b7280';
  const gridColor  = isDark ? '#374151' : '#e5e7eb';
  const cpuColor   = isDark ? '#818cf8' : '#6366f1';
  const ramColor   = isDark ? '#34d399' : '#10b981';

  if (isLoading) {
    return (
      <div className="space-y-2 py-2">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-8 w-full rounded" />
        ))}
      </div>
    );
  }

  if (isError || !data || data.length === 0) {
    return <EmptyState />;
  }

  const chartData = data.map((d: AppCostEntry) => ({
    name: truncate(d.app_name),
    fullName: d.app_name,
    CPU: d.cpu_cost_usd,
    RAM: d.ram_cost_usd,
  }));

  const chartHeight = Math.max(160, chartData.length * 52 + 60);
  const longestName = Math.max(...chartData.map((d) => d.name.length));
  const yAxisWidth = Math.min(Math.max(longestName * 7, 100), 220);

  return (
    <div className="w-full">
      <div className="mb-1 flex items-center justify-end pr-1">
        <span className="text-xs text-muted-foreground">30-day estimate · CPU €0.048/core·h · RAM €0.006/GiB·h</span>
      </div>
      <ResponsiveContainer width="100%" height={chartHeight}>
        <BarChart
          data={chartData}
          layout="vertical"
          margin={{ top: 4, right: 64, left: 0, bottom: 4 }}
          barSize={20}
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
          <Tooltip content={<CustomTooltip />} cursor={{ fill: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)' }} />
          <Legend
            iconType="circle"
            iconSize={8}
            wrapperStyle={{ fontSize: 12, color: textColor, paddingTop: 12 }}
          />
          <Bar dataKey="CPU" stackId="cost" fill={cpuColor} radius={[0, 0, 0, 0]}>
            {chartData.map((_, i) => (
              <Cell key={i} fill={cpuColor} />
            ))}
          </Bar>
          <Bar dataKey="RAM" stackId="cost" fill={ramColor} radius={[0, 4, 4, 0]}>
            {chartData.map((_, i) => (
              <Cell key={i} fill={ramColor} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
