import { IconSun } from '@tabler/icons-react';
import { Breadcrumb } from '@/components/Breadcrumb';
import { useBreadcrumb } from './BreadcrumbContext';

export function TopNav() {
  const { items } = useBreadcrumb();

  return (
    <header className="h-12 flex items-center px-4 border-b border-border bg-background shrink-0">
      {/* Left: breadcrumb (poussé par les layouts enfants via useBreadcrumb) */}
      <Breadcrumb items={items} />

      {/* Right: dark/light stub + Docs */}
      <div className="flex items-center gap-1 ml-auto">
        <button
          className="h-7 w-7 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
          aria-label="Thème"
        >
          <IconSun size={16} />
        </button>

        <a
          href="https://docs.cloud-native-plat4k.io"
          target="_blank"
          rel="noreferrer"
          className="h-7 px-2.5 flex items-center text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-accent rounded-md transition-colors"
        >
          Docs
        </a>
      </div>
    </header>
  );
}
