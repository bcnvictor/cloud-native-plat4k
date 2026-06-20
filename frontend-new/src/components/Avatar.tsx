import { cn } from '@/lib/cn';
import { getInitials, getAvatarColor } from '@/utils/initials';

interface AvatarProps {
  name: string;
  size?: 'sm' | 'md' | 'lg';
  shape?: 'circle' | 'rounded';
  className?: string;
}

const SIZES = {
  sm: 'h-6 w-6 text-xs',
  md: 'h-7 w-7 text-xs',
  lg: 'h-8 w-8 text-sm',
};

export function Avatar({ name, size = 'md', shape = 'circle', className }: AvatarProps) {
  return (
    <div
      className={cn(
        'flex items-center justify-center font-medium shrink-0',
        shape === 'circle' ? 'rounded-full' : 'rounded-md',
        getAvatarColor(name),
        SIZES[size],
        className
      )}
    >
      {getInitials(name)}
    </div>
  );
}
