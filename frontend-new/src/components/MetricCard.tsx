import React from 'react';
import { ResponsiveContainer, LineChart, Line } from 'recharts';
import { cn } from '@/lib/cn';

export interface SparkPoint { t: number; v: number }

interface MetricCardProps {
  label: string;
  value: string | number;
  unit?: string;
  icon?: React.ReactNode;
  sublabel?: string;
  sparkline?: SparkPoint[];
  className?: string;
}

export function MetricCard({ label, value, unit, icon, sublabel, sparkline, className }: MetricCardProps) {
  return (
    <div className={cn('bg-background border border-border rounded-lg overflow-hidden', className)}>
      <div className="px-4 pt-4 pb-3">
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs text-zinc-400 font-normal uppercase tracking-wide">{label}</p>
          {icon && <span className="text-zinc-300">{icon}</span>}
        </div>
        <p className="text-2xl font-semibold text-zinc-900">
          {value}
          {unit && <span className="text-xs text-muted-foreground ml-1">{unit}</span>}
        </p>
        {sublabel && <p className="text-xs text-muted-foreground mt-0.5">{sublabel}</p>}
      </div>

      {sparkline && sparkline.length > 0 && (
        <div className="border-t border-border/40">
          <ResponsiveContainer width="100%" height={40}>
            <LineChart data={sparkline} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
              <Line
                type="monotone"
                dataKey="v"
                stroke="var(--primary)"
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
