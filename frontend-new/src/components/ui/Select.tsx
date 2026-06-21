import React, { createContext, useContext, useState, useRef, useEffect } from 'react';
import { IconChevronDown, IconCheck } from '@tabler/icons-react';
import { cn } from '@/utils/cn';

// ─── Context ──────────────────────────────────────────────────────────────────

interface SelectCtx {
  value: string;
  open: boolean;
  onSelect: (v: string) => void;
  setOpen: (v: boolean) => void;
}

const SelectContext = createContext<SelectCtx>({
  value: '',
  open: false,
  onSelect: () => {},
  setOpen: () => {},
});

// ─── SelectRoot ───────────────────────────────────────────────────────────────

interface SelectRootProps {
  value: string;
  onValueChange: (v: string) => void;
  children: React.ReactNode;
  disabled?: boolean;
}

export function SelectRoot({ value, onValueChange, children, disabled }: SelectRootProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    if (open) document.addEventListener('mousedown', onOutside);
    return () => document.removeEventListener('mousedown', onOutside);
  }, [open]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    if (open) document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  return (
    <SelectContext.Provider
      value={{
        value,
        open: disabled ? false : open,
        onSelect: onValueChange,
        setOpen: disabled ? () => {} : setOpen,
      }}
    >
      <div ref={ref} className="relative">
        {children}
      </div>
    </SelectContext.Provider>
  );
}

// ─── SelectTrigger ────────────────────────────────────────────────────────────

interface SelectTriggerProps {
  children: React.ReactNode;
  className?: string;
  disabled?: boolean;
}

export function SelectTrigger({ children, className, disabled }: SelectTriggerProps) {
  const { open, setOpen } = useContext(SelectContext);
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => setOpen(!open)}
      className={cn(
        'flex h-8 w-full items-center justify-between gap-2 px-3 text-sm rounded-md',
        'border border-input bg-background text-left',
        'focus:outline-none focus:ring-2 focus:ring-ring',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        className
      )}
    >
      <span className="flex-1 truncate">{children}</span>
      <IconChevronDown
        size={14}
        className={cn('text-muted-foreground shrink-0 transition-transform', open && 'rotate-180')}
      />
    </button>
  );
}

// ─── SelectValue ──────────────────────────────────────────────────────────────

export function SelectValue({ placeholder }: { placeholder?: string }) {
  const { value } = useContext(SelectContext);
  return (
    <span className={cn(!value && 'text-muted-foreground')}>
      {value || placeholder || 'Sélectionner…'}
    </span>
  );
}

// ─── SelectContent ────────────────────────────────────────────────────────────

interface SelectContentProps {
  children: React.ReactNode;
  className?: string;
}

export function SelectContent({ children, className }: SelectContentProps) {
  const { open } = useContext(SelectContext);
  if (!open) return null;
  return (
    <div
      className={cn(
        'absolute left-0 right-0 top-full mt-1 z-50',
        'bg-background border border-border rounded-md shadow-md',
        'py-1 max-h-60 overflow-y-auto',
        className
      )}
    >
      {children}
    </div>
  );
}

// ─── SelectItem ───────────────────────────────────────────────────────────────

interface SelectItemProps {
  value: string;
  children: React.ReactNode;
  disabled?: boolean;
  className?: string;
}

export function SelectItem({ value, children, disabled, className }: SelectItemProps) {
  const { value: selected, onSelect, setOpen } = useContext(SelectContext);
  const isSelected = selected === value;

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => {
        onSelect(value);
        setOpen(false);
      }}
      className={cn(
        'w-full flex items-center gap-2 px-3 py-1.5 text-sm text-left transition-colors',
        'hover:bg-accent hover:text-accent-foreground',
        'disabled:opacity-40 disabled:pointer-events-none',
        isSelected && 'bg-accent text-accent-foreground font-medium',
        className
      )}
    >
      <span className="w-3 shrink-0 flex items-center justify-center">
        {isSelected && <IconCheck size={11} />}
      </span>
      {children}
    </button>
  );
}

// ─── Select (high-level wrapper, keeps existing API) ─────────────────────────

interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

interface SelectProps {
  label?: string;
  options: SelectOption[];
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  hint?: string;
  disabled?: boolean;
  className?: string;
}

export function Select({
  label,
  options,
  value,
  onChange,
  placeholder,
  hint,
  disabled,
  className,
}: SelectProps) {
  const id = label?.toLowerCase().replace(/\s+/g, '-');
  const displayLabel = options.find((o) => o.value === value)?.label;

  return (
    <div className="flex flex-col gap-1">
      {label && (
        <label htmlFor={id} className="text-sm font-medium text-foreground">
          {label}
        </label>
      )}
      <SelectRoot value={value} onValueChange={onChange} disabled={disabled}>
        <SelectTrigger className={className}>
          <span className={cn('truncate', !displayLabel && 'text-muted-foreground')}>
            {displayLabel ?? placeholder ?? 'Sélectionner…'}
          </span>
        </SelectTrigger>
        <SelectContent>
          {options.map((opt) => (
            <SelectItem key={opt.value} value={opt.value} disabled={opt.disabled}>
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </SelectRoot>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}
