import { useRef, type KeyboardEvent } from 'react';
import { IconMessageCircle, IconStethoscope } from '@tabler/icons-react';
import type { RobotMode } from '@/store/doctor';
import { cn } from '@/utils/cn';

const OPTIONS: { value: RobotMode; label: string; Icon: typeof IconStethoscope }[] = [
  { value: 'chat', label: 'Assistant', Icon: IconMessageCircle },
  { value: 'doctor', label: 'Doctor', Icon: IconStethoscope },
];

interface Props {
  mode: RobotMode;
  onChange: (mode: RobotMode) => void;
  className?: string;
}

/**
 * Interrupteur Assistant / Doctor (groupe de boutons radio). Une seule option est
 * dans l'ordre de tabulation ; les flèches, Début et Fin déplacent le choix.
 */
export function ModeToggle({ mode, onChange, className }: Props) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  function onKeyDown(e: KeyboardEvent<HTMLButtonElement>, index: number) {
    const last = OPTIONS.length - 1;
    let next: number | null = null;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = index === last ? 0 : index + 1;
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = index === 0 ? last : index - 1;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = last;
    if (next === null) return;
    e.preventDefault();
    refs.current[next]?.focus();
    onChange(OPTIONS[next].value);
  }

  return (
    <div
      role="radiogroup"
      aria-label="Mode de l'assistant"
      className={cn('inline-flex gap-0.5 rounded-lg border border-border bg-muted p-0.5', className)}
    >
      {OPTIONS.map(({ value, label, Icon }, i) => {
        const checked = mode === value;
        return (
          <button
            key={value}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="radio"
            aria-checked={checked}
            tabIndex={checked ? 0 : -1}
            onClick={() => onChange(value)}
            onKeyDown={(e) => onKeyDown(e, i)}
            className={cn(
              'flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium max-sm:px-2',
              checked
                ? 'bg-card text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            )}
          >
            <Icon size={13} aria-hidden="true" className={cn('max-sm:hidden', checked && 'text-primary')} />
            {label}
          </button>
        );
      })}
    </div>
  );
}
