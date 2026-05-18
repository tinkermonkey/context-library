import { NavItem, type IconName } from '@tinkermonkey/heimdall-ui';

export interface SidebarItem {
  id: string;
  label: string;
  icon?: IconName;
  count?: number;
}

export interface SidebarSection {
  title: string;
  items: SidebarItem[];
}

interface SidebarProps {
  sections: SidebarSection[];
  activeItemId?: string;
  collapsed?: boolean;
  onCollapse?: (collapsed: boolean) => void;
  onSelectItem?: (itemId: string) => void;
  appTitle?: string;
}

export function Sidebar({
  sections,
  activeItemId,
  onSelectItem,
  appTitle = 'Context Library',
}: SidebarProps) {
  return (
    <aside
      className="flex flex-col h-full"
      style={{
        background: 'rgb(var(--shell-bg))',
        borderRight: '1px solid rgb(var(--shell-border))',
        width: '240px',
      }}
      aria-label="Main navigation"
    >
      {/* Header */}
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
          {appTitle}
        </span>
      </div>

      {/* Navigation */}
      <nav
        className="flex-1 overflow-y-auto pt-4"
        aria-label="Primary navigation"
      >
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

                return (
                  <NavItem
                    key={item.id}
                    icon={item.icon}
                    label={item.label}
                    count={item.count}
                    active={isActive}
                    onClick={() => onSelectItem?.(item.id)}
                  />
                );
              })}
            </div>
          </div>
        ))}
      </nav>
    </aside>
  );
}
