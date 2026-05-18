import type { ComponentType, SVGProps } from 'react';

export type HeroIcon = ComponentType<SVGProps<SVGSVGElement>>;

export interface NavItem {
  id: string;
  label: string;
  icon: HeroIcon;
}

export interface NavigationSection {
  title: string;
  items: NavItem[];
}

interface NavigationSidebarProps {
  sections: NavigationSection[];
  activeItemId?: string;
  onSelectItem?: (itemId: string) => void;
  className?: string;
}


export function NavigationSidebar({
  sections,
  activeItemId,
  onSelectItem,
  className = '',
}: NavigationSidebarProps) {

  return (
    <div
      className={`flex flex-col h-full ${className}`}
      style={{
        background: 'rgb(var(--shell-bg))',
        borderRight: '1px solid rgb(var(--shell-border))',
        width: '240px',
      }}
    >
      {/* Sidebar header with app title */}
      <div
        className="flex items-center justify-center h-14 border-b"
        style={{
          borderColor: 'rgb(var(--shell-border))',
          paddingTop: '8px',
          paddingBottom: '8px',
        }}
      >
        <span
          className="text-sm font-semibold"
          style={{ color: 'rgb(var(--shell-fg-1))' }}
        >
          Context Library
        </span>
      </div>

      {/* Navigation sections */}
      <nav className="flex-1 overflow-y-auto pt-4">
        {sections.map((section) => (
          <div key={section.title} className="px-2">
            <div
              className="text-xs font-semibold px-3 py-2 mb-2"
              style={{ color: 'rgb(var(--shell-fg-3))' }}
            >
              {section.title}
            </div>
            <div className="space-y-1">
              {section.items.map((item) => {
                const isActive = activeItemId === item.id;
                const Icon = item.icon;

                return (
                  <button
                    key={item.id}
                    onClick={() => onSelectItem?.(item.id)}
                    className="w-full flex items-center gap-3 px-3 py-2 rounded-lg transition-colors"
                    style={{
                      background: isActive ? 'rgb(var(--shell-surface))' : 'transparent',
                      color: isActive
                        ? 'rgb(var(--shell-fg-1))'
                        : 'rgb(var(--shell-fg-2))',
                    }}
                    onMouseEnter={(e) => {
                      if (!isActive) {
                        e.currentTarget.style.background = 'rgb(var(--shell-surface))';
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (!isActive) {
                        e.currentTarget.style.background = 'transparent';
                      }
                    }}
                  >
                    <Icon className="w-5 h-5 shrink-0" />
                    <span className="text-sm font-medium truncate">
                      {item.label}
                    </span>
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
