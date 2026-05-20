import { useEffect, useState } from 'react';
import { useRouter } from '@tanstack/react-router';
import { CommandPalette, type Command } from '@tinkermonkey/heimdall-ui';
import { useAdminAdapters } from '../hooks/useAdminAdapters';
import { triggerAdapterSync } from '../api/client';
import { useToast } from '../hooks/useToast';
import { type ValidRoute } from './Layout';

interface NavItem {
  id: ValidRoute;
  label: string;
}

export function CommandPaletteWrapper({
  primaryNav,
  adminNav,
}: {
  primaryNav: readonly NavItem[];
  adminNav: NavItem;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const router = useRouter();
  const { data: adaptersData } = useAdminAdapters();
  const { showToast } = useToast();

  // Listen for Cmd+K / Ctrl+K
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setIsOpen((prev) => !prev);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Build navigation commands
  const navigationCommands: Command[] = [
    ...primaryNav.map((item) => ({
      id: `nav-${item.id}`,
      label: item.label,
      onSelect: () => {
        router.navigate({ to: item.id });
      },
    })),
    {
      id: `nav-${adminNav.id}`,
      label: adminNav.label,
      onSelect: () => {
        router.navigate({ to: adminNav.id });
      },
    },
  ];

  // Build adapter sync commands
  const adapterCommands: Command[] = (adaptersData?.adapters || []).map((adapter) => ({
    id: `sync-${adapter.adapter_id}`,
    label: `Sync ${adapter.adapter_type}`,
    description: adapter.adapter_id,
    onSelect: async () => {
      try {
        await triggerAdapterSync(adapter.adapter_id);
        showToast({
          title: `Started sync for ${adapter.adapter_type}`,
          variant: 'success',
          duration: 3000,
        });
      } catch (error) {
        showToast({
          title: `Failed to sync ${adapter.adapter_type}`,
          subtitle: error instanceof Error ? error.message : 'Unknown error',
          variant: 'error',
          duration: 4000,
        });
      }
    },
  }));

  const allCommands = [...navigationCommands, ...adapterCommands];

  return (
    <CommandPalette
      isOpen={isOpen}
      onClose={() => setIsOpen(false)}
      commands={allCommands}
      placeholder="Search navigation or commands..."
    />
  );
}
