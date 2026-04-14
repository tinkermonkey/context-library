import { Link, useRouterState } from '@tanstack/react-router';
import {
  Squares2X2Icon,
  MagnifyingGlassIcon,
  DocumentTextIcon,
  ChatBubbleLeftIcon,
  CalendarIcon,
  CheckCircleIcon,
  HeartIcon,
  FolderIcon,
  UsersIcon,
  MapPinIcon,
  MusicalNoteIcon,
  Cog6ToothIcon,
} from '@heroicons/react/24/outline';
import type { ComponentType, SVGProps } from 'react';

// NOTE: `to` is typed as string rather than TanStack Router's inferred path union
// because data-array nav configs lose generic inference. All paths are validated
// at runtime by the router; mis-typed paths produce a console warning in dev.
interface NavItem {
  label: string;
  to: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
}

const PRIMARY_NAV: NavItem[] = [
  { label: 'Dashboard', to: '/', icon: Squares2X2Icon },
  { label: 'Search', to: '/search', icon: MagnifyingGlassIcon },
  { label: 'Notes', to: '/notes', icon: DocumentTextIcon },
  { label: 'Messages', to: '/messages', icon: ChatBubbleLeftIcon },
  { label: 'Events', to: '/events', icon: CalendarIcon },
  { label: 'Tasks', to: '/tasks', icon: CheckCircleIcon },
  { label: 'Health', to: '/health', icon: HeartIcon },
  { label: 'Documents', to: '/documents', icon: FolderIcon },
  { label: 'People', to: '/people', icon: UsersIcon },
  { label: 'Location', to: '/location', icon: MapPinIcon },
  { label: 'Music', to: '/music', icon: MusicalNoteIcon },
];

const ADMIN_NAV: NavItem = { label: 'Admin', to: '/admin', icon: Cog6ToothIcon };

const BASE_LINK =
  'flex items-center gap-2.5 mx-2 px-3 h-9 rounded-[6px] text-[13px] transition-colors no-underline';
const ACTIVE_LINK = 'bg-indigo-500 text-white font-medium';
const INACTIVE_LINK = 'text-[#9CA3AF] hover:bg-[#1A1A1A] hover:text-white';

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  const { icon: Icon, label, to } = item;
  return (
    <Link
      to={to}
      className={`${BASE_LINK} ${active ? ACTIVE_LINK : INACTIVE_LINK}`}
      aria-current={active ? 'page' : undefined}
    >
      <Icon
        aria-hidden="true"
        className={`w-4 h-4 shrink-0 ${active ? 'text-white' : 'text-[#6B7280]'}`}
      />
      {label}
    </Link>
  );
}

export function Sidebar() {
  const { location } = useRouterState();
  const path = location.pathname;

  const isActive = (to: string) => {
    if (to === '/') return path === '/';
    return path === to || path.startsWith(to + '/');
  };

  return (
    // hidden on mobile, visible flex column from xl (1280px) upward
    <aside
      aria-label="Main navigation"
      className="hidden xl:flex flex-col shrink-0 h-screen sticky top-0 w-[220px] min-w-[220px] border-r border-[#1E1E1E]"
      style={{ background: '#111111' }}
    >
      {/* Logo */}
      <div className="flex items-center gap-2 shrink-0 px-5 h-14">
        <div className="w-6 h-6 rounded-[6px] bg-indigo-500 shrink-0" aria-hidden="true" />
        <span className="text-white font-semibold text-sm leading-none">Context Library</span>
      </div>

      {/* Divider */}
      <div className="h-px shrink-0 bg-[#1E1E1E]" />

      {/* Primary nav */}
      <nav
        aria-label="Primary navigation"
        className="flex flex-col py-2 gap-0.5 flex-1 overflow-y-auto"
      >
        {PRIMARY_NAV.map((item) => (
          <NavLink key={item.to} item={item} active={isActive(item.to)} />
        ))}

        {/* Divider before Admin */}
        <div className="h-px mx-2 my-1 shrink-0 bg-[#1E1E1E]" />

        <NavLink item={ADMIN_NAV} active={isActive(ADMIN_NAV.to)} />
      </nav>
    </aside>
  );
}
