import type { ComponentType, SVGProps } from 'react';
import { Bars3Icon } from '@heroicons/react/24/outline';

type HeroIcon = ComponentType<SVGProps<SVGSVGElement>>;

interface NavItem {
  id: string;
  label: string;
  icon: HeroIcon;
}

interface NavigationSection {
  title: string;
  items: NavItem[];
}

interface NavigationSidebarProps {
  sections: NavigationSection[];
  activeItemId?: string;
  collapsed?: boolean;
  onCollapse?: (collapsed: boolean) => void;
  onSelectItem?: (itemId: string) => void;
  className?: string;
}


export function NavigationSidebar({
  sections,
  activeItemId,
  collapsed = false,
  onCollapse,
  onSelectItem,
  className = '',
}: NavigationSidebarProps) {

  return (
    <div
      className={`flex flex-col h-full bg-zinc-900 border-r border-zinc-800 ${className}`}
      style={{ width: collapsed ? '70px' : '240px' }}
    >
      {/* Collapse button */}
      <button
        onClick={() => onCollapse?.(!collapsed)}
        className="flex items-center justify-center h-14 border-b border-zinc-800 hover:bg-zinc-800 transition-colors"
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        <Bars3Icon className="w-5 h-5" style={{ color: 'rgb(var(--shell-fg-2))' }} />
      </button>

      {/* Navigation sections */}
      <nav className="flex-1 overflow-y-auto pt-4">
        {sections.map((section) => (
          <div key={section.title} className="px-2">
            {!collapsed && (
              <div
                className="text-xs font-semibold px-3 py-2 mb-2"
                style={{ color: 'rgb(var(--shell-fg-3))' }}
              >
                {section.title}
              </div>
            )}
            <div className="space-y-1">
              {section.items.map((item) => {
                const isActive = activeItemId === item.id;
                const Icon = item.icon;

                return (
                  <button
                    key={item.id}
                    onClick={() => onSelectItem?.(item.id)}
                    className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg transition-colors ${
                      isActive
                        ? 'bg-zinc-700'
                        : 'hover:bg-zinc-800'
                    }`}
                    title={collapsed ? item.label : undefined}
                    style={{
                      color: isActive
                        ? 'rgb(var(--shell-fg-1))'
                        : 'rgb(var(--shell-fg-2))',
                    }}
                  >
                    <Icon className="w-5 h-5 shrink-0" />
                    {!collapsed && (
                      <span className="text-sm font-medium truncate">
                        {item.label}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </nav>
    </div>
  );
}
