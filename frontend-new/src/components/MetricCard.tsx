import React from 'react';
import { ResponsiveContainer, AreaChart, Area } from 'recharts';
import { IconExternalLink, IconClock } from '@tabler/icons-react';
import { cn } from '@/utils/cn';

export interface SparkPoint { t: number; v: number }

interface MetricCardProps {
  label: string;
  value: React.ReactNode;
  unit?: string;
  icon?: React.ReactNode;
  sublabel?: React.ReactNode;
  sparkline?: SparkPoint[];
  externalUrl?: string;
  className?: string;
}

const isEmpty = (v: React.ReactNode) =>
  v === null || v === undefined || v === 0 || v === '—';

export function MetricCard({ label, value, unit, icon, sublabel, sparkline, externalUrl, className }: MetricCardProps) {
  const isPrimitive = typeof value === 'string' || typeof value === 'number';
  const empty = isEmpty(value);

  return (
    <div className={cn('bg-background border border-border rounded-lg overflow-hidden', className)}>
      <div className="px-4 pt-4 pb-3">
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs text-zinc-400 font-normal uppercase tracking-wide">{label}</p>
          <div className="flex items-center gap-1.5">
            {icon && <span className="text-zinc-300">{icon}</span>}
            {externalUrl && (
              <a
                href={externalUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-zinc-400 hover:text-zinc-200 transition-colors"
                title="Voir dans Grafana"
              >
                <IconExternalLink size={11} />
              </a>
            )}
          </div>
        </div>

        {empty ? (
          <div className="flex flex-col items-center justify-center gap-1 py-2">
            <IconClock size={18} className="text-zinc-300" />
            <span className="text-xs text-zinc-400">Waiting for stats...</span>
          </div>
        ) : isPrimitive ? (
          <p className="text-2xl font-semibold text-foreground">
            {value}
            {unit && <span className="text-xs text-muted-foreground ml-1">{unit}</span>}
          </p>
        ) : (
          <div className="mt-1">{value}</div>
        )}

        {!empty && sublabel && <div className="text-xs mt-1">{sublabel}</div>}
      </div>

      {!empty && sparkline && sparkline.length > 0 && (
        <div className="border-t border-border/40">
          <ResponsiveContainer width="100%" height={40}>
            <AreaChart data={sparkline} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
              <Area
                type="monotone"
                dataKey="v"
                stroke="#007BA7"
                strokeWidth={1.5}
                fill="#007BA7"
                fillOpacity={0.08}
                dot={false}
                isAnimationActive={false}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
