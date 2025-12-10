'use client';

import { cn } from '@/lib/cn';
import { Bot, Zap, Brain, Wrench, Anchor } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

type IconName = 'agent' | 'command' | 'skill' | 'tool' | 'hook';

interface PrimitiveCardProps {
  icon: IconName;
  name: string;
  description: string;
  invocation: string;
  color: 'indigo' | 'purple' | 'pink' | 'cyan' | 'green';
}

const iconMap: Record<IconName, LucideIcon> = {
  agent: Bot,
  command: Zap,
  skill: Brain,
  tool: Wrench,
  hook: Anchor,
};

const colorStyles = {
  indigo: {
    bg: 'bg-indigo-500/10 dark:bg-indigo-500/20',
    border: 'border-indigo-500/30',
    badge: 'bg-indigo-500/20 text-indigo-700 dark:text-indigo-300 border-indigo-500/40',
    iconBg: 'bg-indigo-500/20',
    icon: 'text-indigo-600 dark:text-indigo-400',
  },
  purple: {
    bg: 'bg-purple-500/10 dark:bg-purple-500/20',
    border: 'border-purple-500/30',
    badge: 'bg-purple-500/20 text-purple-700 dark:text-purple-300 border-purple-500/40',
    iconBg: 'bg-purple-500/20',
    icon: 'text-purple-600 dark:text-purple-400',
  },
  pink: {
    bg: 'bg-pink-500/10 dark:bg-pink-500/20',
    border: 'border-pink-500/30',
    badge: 'bg-pink-500/20 text-pink-700 dark:text-pink-300 border-pink-500/40',
    iconBg: 'bg-pink-500/20',
    icon: 'text-pink-600 dark:text-pink-400',
  },
  cyan: {
    bg: 'bg-cyan-500/10 dark:bg-cyan-500/20',
    border: 'border-cyan-500/30',
    badge: 'bg-cyan-500/20 text-cyan-700 dark:text-cyan-300 border-cyan-500/40',
    iconBg: 'bg-cyan-500/20',
    icon: 'text-cyan-600 dark:text-cyan-400',
  },
  green: {
    bg: 'bg-emerald-500/10 dark:bg-emerald-500/20',
    border: 'border-emerald-500/30',
    badge: 'bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 border-emerald-500/40',
    iconBg: 'bg-emerald-500/20',
    icon: 'text-emerald-600 dark:text-emerald-400',
  },
};

export function PrimitiveCard({ icon, name, description, invocation, color }: PrimitiveCardProps) {
  const styles = colorStyles[color];
  const Icon = iconMap[icon];

  return (
    <div className={cn(
      'relative rounded-xl border p-4 transition-all hover:scale-[1.02]',
      styles.bg,
      styles.border
    )}>
      <div className="flex items-center gap-3 mb-2">
        <div className={cn('flex h-9 w-9 items-center justify-center rounded-lg', styles.iconBg)}>
          <Icon className={cn('w-5 h-5', styles.icon)} />
        </div>
        <span className="font-semibold text-fd-foreground">{name}</span>
      </div>
      <p className="text-sm text-fd-muted-foreground mb-3">{description}</p>
      <code className={cn(
        'inline-block px-2 py-1 rounded-md text-xs font-mono border',
        styles.badge
      )}>
        {invocation}
      </code>
    </div>
  );
}

export function PrimitiveGrid({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 my-6">
      {children}
    </div>
  );
}
