import { cn } from '@/utils/cn';

interface Tab {
  key: string;
  label: string;
}

interface TabsProps {
  tabs: Tab[];
  active: string;
  onChange: (key: string) => void;
  className?: string;
}

export function Tabs({ tabs, active, onChange, className }: TabsProps) {
  return (
    <div className={cn('flex border-b border-border', className)}>
      {tabs.map((tab) => (
        <button
          key={tab.key}
          onClick={() => onChange(tab.key)}
          className={cn(
            'px-4 py-2.5 text-sm transition-colors -mb-px border-b-2',
            active === tab.key
              ? 'font-medium text-foreground border-foreground'
              : 'text-muted-foreground border-transparent hover:text-foreground'
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
