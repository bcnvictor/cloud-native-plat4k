import { IconCheck } from '@tabler/icons-react';
import { cn } from '@/utils/cn';

type StepState = 'active' | 'done' | 'todo';

interface StepperStep {
  label: string;
  state: StepState;
}

interface StepperBarProps {
  steps: StepperStep[];
  onStepClick?: (index: number) => void;
  locked?: boolean;
}

export function StepperBar({ steps, onStepClick, locked = false }: StepperBarProps) {
  return (
    <div className="flex items-center gap-0 mb-8">
      {steps.flatMap((step, i) => {
        const clickable = step.state === 'done' && !locked;
        const circle = (
          <button
            key={`step-${i}`}
            type="button"
            onClick={() => clickable && onStepClick?.(i)}
            className={cn(
              'w-9 h-9 rounded-full text-sm font-semibold flex items-center justify-center shrink-0 transition-colors',
              step.state === 'active' && 'bg-primary text-white cursor-default',
              step.state === 'done' && !locked && 'bg-primary text-white cursor-pointer hover:bg-primary/80',
              step.state === 'done' && locked && 'bg-primary text-white cursor-not-allowed opacity-60',
              step.state === 'todo' && 'bg-muted text-muted-foreground cursor-default',
            )}
          >
            {step.state === 'done' ? (
              <IconCheck size={14} strokeWidth={2.5} />
            ) : (
              i + 1
            )}
          </button>
        );
        const line =
          i < steps.length - 1 ? (
            <div key={`line-${i}`} className="flex-1 h-0.5 bg-border" />
          ) : null;
        return line ? [circle, line] : [circle];
      })}
    </div>
  );
}
