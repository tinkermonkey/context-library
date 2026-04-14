import { Cog6ToothIcon } from '@heroicons/react/24/outline';
import { colors } from '../lib/designTokens';

export default function AdminPage() {
  return (
    <div className="flex flex-col items-center justify-center h-full min-h-[60vh] gap-4">
      <div
        className="flex items-center justify-center rounded-2xl"
        style={{ width: 64, height: 64, background: `${colors.accent}1A` }}
      >
        <Cog6ToothIcon className="w-8 h-8" style={{ color: colors.textMuted }} />
      </div>
      <div className="text-center">
        <h2 className="text-white font-semibold text-lg mb-1">Admin</h2>
        <p className="text-sm text-[#6B7280]">
          Adapter health, connector status, and administrative actions.
          <br />
          Coming in issue{' '}
          <a
            href="https://github.com/tinkermonkey/context-library/issues/450"
            className="hover:underline"
            style={{ color: colors.accent }}
          >
            #450
          </a>.
        </p>
      </div>
    </div>
  );
}
