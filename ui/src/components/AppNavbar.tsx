import { useRouterState, Link } from '@tanstack/react-router';
import type { ReactNode } from 'react';
import { Navbar, NavbarBrand, NavbarCollapse, NavbarLink, NavbarToggle } from 'flowbite-react';
import { HealthIndicator } from './HealthIndicator';

interface NavbarLinkRouterProps {
  to: string;
  active: boolean;
  children: ReactNode;
}

function NavbarLinkRouter({ to, active, children }: NavbarLinkRouterProps) {
  return (
    <NavbarLink
      as={Link}
      href={to}
      active={active}
      // @ts-expect-error: NavbarLink extends HTMLAnchorElement props (href), but when as={Link},
      // the component renders as TanStack Router's Link which requires 'to' prop instead of 'href'.
      // This is safe because Flowbite forwards component props through the 'as' polymorphism.
      to={to}
    >
      {children}
    </NavbarLink>
  );
}

export function AppNavbar() {
  const routerState = useRouterState();
  const currentPath = routerState.location.pathname;

  const isActive = (path: string) => currentPath === path;

  return (
    <Navbar fluid>
      <NavbarBrand as="div">
        <span className="self-center whitespace-nowrap text-xl font-semibold">Context Library</span>
      </NavbarBrand>
      <NavbarToggle />
      <NavbarCollapse>
        <NavbarLinkRouter to="/" active={isActive('/')}>
          Dashboard
        </NavbarLinkRouter>
        <NavbarLinkRouter to="/browser" active={isActive('/browser')}>
          Data Browser
        </NavbarLinkRouter>
        <NavbarLinkRouter to="/search" active={isActive('/search')}>
          Semantic Search
        </NavbarLinkRouter>
      </NavbarCollapse>
      <div className="ml-auto">
        <HealthIndicator />
      </div>
    </Navbar>
  );
}
