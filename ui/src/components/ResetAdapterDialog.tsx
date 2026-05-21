import { useState, useRef } from 'react';
import { Modal, ConfirmDialog, Button, Icon } from '@tinkermonkey/heimdall-ui';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { resetAdapter } from '../api/client';
import { useToast } from '../hooks/useToast';
import type { AdapterResetResponse } from '../types/api';

interface ResetAdapterDialogProps {
  adapterId: string;
  adapterName: string;
  isOpen: boolean;
  onClose: () => void;
}

/**
 * Modal dialog for resetting an adapter with confirmation, progress, and results.
 * Handles the reset operation and invalidates related queries on success.
 */
export function ResetAdapterDialog({
  adapterId,
  adapterName,
  isOpen,
  onClose,
}: ResetAdapterDialogProps) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [showResult, setShowResult] = useState(false);
  const [result, setResult] = useState<AdapterResetResponse | null>(null);
  const confirmedRef = useRef(false);

  const resetMutation = useMutation({
    mutationFn: () => resetAdapter(adapterId),
    onSuccess: (data) => {
      setResult(data);
      showToast({
        title: 'Adapter reset',
        subtitle: `${adapterName} reset successfully`,
        variant: data.errors.length === 0 ? 'success' : 'warning',
        duration: 4000,
      });
      // Invalidate related queries
      queryClient.invalidateQueries({ queryKey: ['adapters'] });
      queryClient.invalidateQueries({ queryKey: ['adapter-stats'] });
      queryClient.invalidateQueries({ queryKey: ['sources'] });
    },
    onError: (err) => {
      showToast({
        title: 'Reset failed',
        subtitle: err instanceof Error ? err.message : 'Unknown error',
        variant: 'error',
        duration: 4000,
      });
    },
  });

  const confirmMessage = (
    <div className="space-y-4">
      <p style={{ color: 'rgb(var(--canvas-fg-2))' }}>
        Are you sure you want to reset the adapter{' '}
        <strong>{adapterName}</strong>?
      </p>
      <div className="rounded-lg p-3 text-sm" style={{ background: `rgb(var(--status-amber) / 0.13)`, border: `1px solid rgb(var(--status-amber) / 0.3)`, color: 'rgb(var(--status-amber))' }}>
        <p className="font-semibold mb-1">⚠️ This action cannot be undone</p>
        <ul className="list-disc list-inside space-y-1 text-xs">
          <li>All chunks from this adapter will be retired</li>
          <li>Fetch state will be reset</li>
          <li>Helper state (if applicable) will be cleared</li>
          <li>Re-ingestion will be triggered automatically</li>
        </ul>
      </div>
    </div>
  );

  const handleConfirm = () => {
    confirmedRef.current = true;
    setShowResult(true);
    resetMutation.mutate();
  };

  const handleCloseConfirm = () => {
    // Only close parent if not transitioning to result phase
    if (!confirmedRef.current) {
      resetMutation.reset();
      onClose();
    }
  };

  const handleCloseResult = () => {
    setShowResult(false);
    setResult(null);
    confirmedRef.current = false;
    onClose();
  };

  const getResultTitle = () => {
    if (resetMutation.isPending) return 'Resetting Adapter...';
    if (resetMutation.isError) return 'Reset Failed';
    return 'Reset Complete';
  };

  if (!isOpen) return null;

  if (!showResult) {
    return (
      <ConfirmDialog
        isOpen={isOpen}
        onClose={handleCloseConfirm}
        onConfirm={handleConfirm}
        title="Reset Adapter"
        message={confirmMessage}
        confirmLabel="Reset Adapter"
        variant="danger"
      />
    );
  }

  return (
    <Modal isOpen={isOpen} onClose={handleCloseResult} title={getResultTitle()}>
      <div className="space-y-4">
        {resetMutation.isError && (
          <div className="rounded-lg p-3 text-sm" style={{ background: `rgb(var(--status-error) / 0.13)`, border: `1px solid rgb(var(--status-error) / 0.3)`, color: 'rgb(var(--status-error))' }}>
            <strong>Error:</strong>{' '}
            {resetMutation.error instanceof Error
              ? resetMutation.error.message
              : 'Failed to reset adapter'}
          </div>
        )}

        {result && (
          <>
            {result.errors.length === 0 ? (
              <div className="rounded-lg p-3 text-sm" style={{ background: `rgb(var(--status-ok) / 0.13)`, border: `1px solid rgb(var(--status-ok) / 0.3)`, color: 'rgb(var(--status-ok))' }}>
                <strong>Success!</strong> The adapter has been reset
              </div>
            ) : (
              <div className="rounded-lg p-3 text-sm" style={{ background: `rgb(var(--status-amber) / 0.13)`, border: `1px solid rgb(var(--status-amber) / 0.3)`, color: 'rgb(var(--status-amber))' }}>
                <strong>Partial Success</strong> The reset completed with
                warnings
              </div>
            )}

            <div className="rounded-lg p-4 space-y-3" style={{ background: 'rgb(var(--canvas-surface))' }}>
              <div className="text-sm">
                <p style={{ color: 'rgb(var(--canvas-fg-1))' }}>
                  <span className="font-semibold">Helper Reset:</span>{' '}
                  {result.helper_reset.ok ? '✓ Yes' : '✗ Skipped'}
                </p>
              </div>
              {result.helper_reset.cleared.length > 0 && (
                <div className="text-sm">
                  <p style={{ color: 'rgb(var(--canvas-fg-1))' }}>
                    <span className="font-semibold">Cleared States:</span>{' '}
                    {result.helper_reset.cleared.join(', ')}
                  </p>
                </div>
              )}
              {result.library_reset.sources_reset !== null && (
                <div className="text-sm">
                  <p style={{ color: 'rgb(var(--canvas-fg-1))' }}>
                    <span className="font-semibold">Sources Reset:</span> {result.library_reset.sources_reset}
                  </p>
                </div>
              )}
              {result.library_reset.chunks_retired !== null && (
                <div className="text-sm">
                  <p style={{ color: 'rgb(var(--canvas-fg-1))' }}>
                    <span className="font-semibold">Chunks Retired:</span> {result.library_reset.chunks_retired}
                  </p>
                </div>
              )}
              <div className="text-sm">
                <p style={{ color: 'rgb(var(--canvas-fg-1))' }}>
                  <span className="font-semibold">Re-ingestion Triggered:</span>{' '}
                  {result.reingestion_triggered ? '✓ Yes' : '✗ No'}
                </p>
              </div>
            </div>

            {result.errors.length > 0 && (
              <div className="rounded-lg p-3" style={{ background: `rgb(var(--status-error) / 0.13)`, border: `1px solid rgb(var(--status-error) / 0.3)` }}>
                <p className="font-semibold mb-2 text-sm" style={{ color: 'rgb(var(--status-error))' }}>
                  Details:
                </p>
                <ul className="space-y-1">
                  {result.errors.map((error, idx) => (
                    <li key={idx} className="text-xs" style={{ color: 'rgb(var(--status-error) / 0.9)' }}>
                      • {error}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
        {resetMutation.isPending && (
          <div className="flex items-center justify-center py-8">
            <span style={{ color: 'rgb(var(--canvas-fg-3))' }}>
              <Icon name="spinner" size={24} className="animate-spin" />
            </span>
            <span className="ml-3" style={{ color: 'rgb(var(--canvas-fg-2))' }}>Resetting adapter...</span>
          </div>
        )}
      </div>

      <div className="flex justify-end border-t pt-4 mt-4">
        <Button
          onClick={handleCloseResult}
          variant="secondary"
          disabled={resetMutation.isPending}
        >
          Close
        </Button>
      </div>
    </Modal>
  );
}
