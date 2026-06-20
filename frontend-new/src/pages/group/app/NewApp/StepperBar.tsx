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
    <div className="flex items-center w-full mb-8">
      {steps.map((step, i) => (
        <div key={step.label} className="flex items-center flex-1 last:flex-none">
          <div className="flex items-center gap-2">
            <div
              className={cn(
                'h-6 w-6 rounded-full flex items-center justify-center text-xs font-medium border-2 shrink-0',
                step.state === 'done' &&
                  'bg-muted border-muted text-muted-foreground',
                step.state === 'active' &&
                  'bg-background border-foreground text-foreground',
                step.state === 'todo' &&
                  'bg-muted border-muted text-muted-foreground'
              )}
            >
              {step.state === 'done' ? (
                <IconCheck size={12} strokeWidth={2.5} />
              ) : (
                i + 1
              )}
            </div>
            <span
              className={cn(
                'text-xs',
                step.state === 'active'
                  ? 'font-medium text-foreground'
                  : 'text-muted-foreground'
              )}
            >
              {step.label}
            </span>
          </div>
          {i < steps.length - 1 && (
            <div className="flex-1 h-px bg-border mx-3" />
          )}
        </div>
      ))}
    </div>
  );
}
