import { ReactNode, useEffect, useRef, useState } from 'react';
import { IconInfoCircle } from '@tabler/icons-react';
import { cn } from '@/utils/cn';

interface Props {
  children: ReactNode;
  label?: string;
  className?: string;
}

/** Small "i" button that toggles a popover with reference information. */
export function InfoPopover({ children, label = 'Plus d’informations', className }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    if (open) {
      document.addEventListener('mousedown', onOutside);
      document.addEventListener('keydown', onKey);
    }
    return () => {
      document.removeEventListener('mousedown', onOutside);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className={cn('relative inline-flex', className)}>
      <button
        type="button"
        aria-label={label}
        onClick={() => setOpen((v) => !v)}
        className="text-muted-foreground hover:text-foreground transition-colors"
      >
        <IconInfoCircle size={15} />
      </button>
      {open && (
        <div
          className="absolute right-0 top-6 z-50 w-80 rounded-md border border-border bg-background p-3 text-xs text-foreground shadow-lg"
          role="dialog"
        >
          {children}
        </div>
      )}
    </div>
  );
}
