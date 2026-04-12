import { useState } from 'react';
import { Modal, Button, Spinner } from 'flowbite-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { resetAdapter } from '../api/client';
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
  const [showResult, setShowResult] = useState(false);
  const [result, setResult] = useState<AdapterResetResponse | null>(null);

  const resetMutation = useMutation({
    mutationFn: () => resetAdapter(adapterId),
    onSuccess: (data) => {
      setResult(data);
      setShowResult(true);
      // Invalidate related queries
      queryClient.invalidateQueries({ queryKey: ['adapters'] });
      queryClient.invalidateQueries({ queryKey: ['adapter-stats'] });
      queryClient.invalidateQueries({ queryKey: ['sources'] });
    },
  });

  const handleConfirm = () => {
    resetMutation.mutate();
  };

  const handleClose = () => {
    if (!resetMutation.isPending) {
      setShowResult(false);
      setResult(null);
      resetMutation.reset();
      onClose();
    }
  };

  const handleCloseResult = () => {
    setShowResult(false);
    setResult(null);
    onClose();
  };

  return (
    <Modal show={isOpen} onClose={handleClose} size="md">
      <div className="relative bg-white rounded-lg shadow">
        {!showResult ? (
          <>
            <div className="flex justify-between items-center p-6 border-b">
              <h3 className="text-lg font-semibold text-gray-900">Reset Adapter</h3>
              <button
                onClick={handleClose}
                disabled={resetMutation.isPending}
                className="text-gray-400 hover:text-gray-600"
              >
                ✕
              </button>
            </div>

            <div className="p-6 space-y-4">
              <p className="text-gray-700">
                Are you sure you want to reset the adapter{' '}
                <strong>{adapterName}</strong>?
              </p>
              <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3 text-sm text-yellow-800">
                <p className="font-semibold mb-1">⚠️ This action cannot be undone</p>
                <ul className="list-disc list-inside space-y-1 text-xs">
                  <li>All chunks from this adapter will be retired</li>
                  <li>Fetch state will be reset</li>
                  <li>Helper state (if applicable) will be cleared</li>
                  <li>Re-ingestion will be triggered automatically</li>
                </ul>
              </div>

              {resetMutation.isError && resetMutation.error && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-800">
                  <strong>Error:</strong>{' '}
                  {resetMutation.error instanceof Error
                    ? resetMutation.error.message
                    : 'Failed to reset adapter'}
                </div>
              )}
            </div>

            <div className="flex justify-end gap-3 p-6 border-t">
              <Button
                color="gray"
                onClick={handleClose}
                disabled={resetMutation.isPending}
              >
                Cancel
              </Button>
              <Button
                color="failure"
                onClick={handleConfirm}
                disabled={resetMutation.isPending}
              >
                {resetMutation.isPending ? (
                  <>
                    <Spinner size="sm" className="mr-2" />
                    Resetting...
                  </>
                ) : (
                  'Reset Adapter'
                )}
              </Button>
            </div>
          </>
        ) : (
          <>
            <div className="flex justify-between items-center p-6 border-b">
              <h3 className="text-lg font-semibold text-gray-900">Reset Complete</h3>
              <button
                onClick={handleCloseResult}
                className="text-gray-400 hover:text-gray-600"
              >
                ✕
              </button>
            </div>

            <div className="p-6 space-y-4">
              {result && (
                <>
                  {result.errors.length === 0 ? (
                    <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-sm text-green-800">
                      <strong>Success!</strong> The adapter has been reset
                    </div>
                  ) : (
                    <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3 text-sm text-yellow-800">
                      <strong>Partial Success</strong> The reset completed with
                      warnings
                    </div>
                  )}

                  <div className="bg-gray-50 rounded-lg p-4 space-y-3">
                    <div className="text-sm">
                      <p className="text-gray-700">
                        <span className="font-semibold">Helper Reset:</span>{' '}
                        {result.helper_reset.ok ? '✓ Yes' : '✗ Skipped'}
                      </p>
                    </div>
                    {result.helper_reset.cleared.length > 0 && (
                      <div className="text-sm">
                        <p className="text-gray-700">
                          <span className="font-semibold">Cleared States:</span>{' '}
                          {result.helper_reset.cleared.join(', ')}
                        </p>
                      </div>
                    )}
                    {result.library_reset.sources_reset !== null && (
                      <div className="text-sm">
                        <p className="text-gray-700">
                          <span className="font-semibold">Sources Reset:</span> {result.library_reset.sources_reset}
                        </p>
                      </div>
                    )}
                    {result.library_reset.chunks_retired !== null && (
                      <div className="text-sm">
                        <p className="text-gray-700">
                          <span className="font-semibold">Chunks Retired:</span> {result.library_reset.chunks_retired}
                        </p>
                      </div>
                    )}
                    <div className="text-sm">
                      <p className="text-gray-700">
                        <span className="font-semibold">Re-ingestion Triggered:</span>{' '}
                        {result.reingestion_triggered ? '✓ Yes' : '✗ No'}
                      </p>
                    </div>
                  </div>

                  {result.errors.length > 0 && (
                    <div className="bg-orange-50 border border-orange-200 rounded-lg p-3">
                      <p className="font-semibold text-orange-900 mb-2 text-sm">
                        Details:
                      </p>
                      <ul className="space-y-1">
                        {result.errors.map((error, idx) => (
                          <li key={idx} className="text-xs text-orange-800">
                            • {error}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </>
              )}
            </div>

            <div className="flex justify-end p-6 border-t">
              <Button onClick={handleCloseResult} color="gray">
                Close
              </Button>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
