import { useEffect, useState } from 'react';
import { useRouter } from '@tanstack/react-router';
import { CommandPalette, type Command } from '@tinkermonkey/heimdall-ui';
import { useAdminAdapters } from '../hooks/useAdminAdapters';
import { triggerAdapterSync } from '../api/client';
import { useToast } from '../hooks/useToast';
import { ALL_NAV_ITEMS } from './layoutConfig';

export function CommandPaletteWrapper() {
  const [isOpen, setIsOpen] = useState(false);
  const router = useRouter();
  const { data: adaptersData } = useAdminAdapters(120_000);
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

  const navigationCommands: Command[] = ALL_NAV_ITEMS.map((item) => ({
    id: `nav-${item.id}`,
    label: item.label,
    icon: item.icon,
    onSelect: () => {
      // item.id is always a concrete registered route from ALL_NAV_ITEMS
      router.navigate({ to: item.id as string });
    },
  }));

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

  return (
    <CommandPalette
      isOpen={isOpen}
      onClose={() => setIsOpen(false)}
      commands={[...navigationCommands, ...adapterCommands]}
      placeholder="Search navigation or commands..."
    />
  );
}
