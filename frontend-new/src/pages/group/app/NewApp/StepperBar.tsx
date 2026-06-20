import { IconCheck } from '@tabler/icons-react';
import { cn } from '@/lib/cn';

type StepState = 'active' | 'done' | 'todo';

interface StepperStep {
  label: string;
  state: StepState;
}

interface StepperBarProps {
  steps: StepperStep[];
}

export function StepperBar({ steps }: StepperBarProps) {
  return (
    <div className="flex items-center gap-0 mb-8">
      {steps.flatMap((step, i) => {
        const circle = (
          <div
            key={`step-${i}`}
            className={cn(
              'w-7 h-7 rounded-full text-xs font-medium flex items-center justify-center shrink-0',
              step.state === 'active' || step.state === 'done'
                ? 'bg-primary text-white'
                : 'bg-zinc-100 text-zinc-400'
            )}
          >
            {step.state === 'done' ? (
              <IconCheck size={12} strokeWidth={2.5} />
            ) : (
              i + 1
            )}
          </div>
        );
        const line =
          i < steps.length - 1 ? (
            <div key={`line-${i}`} className="flex-1 h-px bg-zinc-200" />
          ) : null;
        return line ? [circle, line] : [circle];
      })}
    </div>
  );
}
