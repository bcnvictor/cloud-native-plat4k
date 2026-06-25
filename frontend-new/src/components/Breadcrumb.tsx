import { Link } from 'react-router-dom';
import { IconChevronRight } from '@tabler/icons-react';

interface BreadcrumbItem {
  label: string;
  to?: string;
}

interface BreadcrumbProps {
  items: BreadcrumbItem[];
}

export function Breadcrumb({ items }: BreadcrumbProps) {
  return (
    <nav className="flex items-center gap-1 mb-2">
      {items.map((item, i) => {
        const isLast = i === items.length - 1;
        return (
          <span key={i} className="flex items-center gap-1">
            {i > 0 && (
              <IconChevronRight
                size={10}
                className="text-muted-foreground shrink-0"
              />
            )}
            {!isLast && item.to ? (
              <Link
                to={item.to}
                className="text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                {item.label}
              </Link>
            ) : (
              <span
                className={
                  isLast
                    ? 'text-xs text-foreground font-medium'
                    : 'text-xs text-muted-foreground'
                }
              >
                {item.label}
              </span>
            )}
          </span>
        );
      })}
    </nav>
  );
}
