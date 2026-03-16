import { Link } from '@tanstack/react-router';
import { NavbarLink } from 'flowbite-react';
import type { ComponentProps } from 'react';

// Test: Can we just pass it through without the cast?
function NavbarLinkRouter({ to, active, children }: { to: string; active: boolean; children: React.ReactNode }) {
  // Approach 1: Use href with Link as component - let Link interpret it
  return (
    <NavbarLink
      as={Link}
      to={to}  // Direct prop passing
      active={active}
    >
      {children}
    </NavbarLink>
  );
}
