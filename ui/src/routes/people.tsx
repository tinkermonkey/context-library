import { UsersIcon } from '@heroicons/react/24/outline';
import { getDomainColor } from '../lib/designTokens';

const color = getDomainColor('people');

export default function PeoplePage() {
  return (
    <div className="flex flex-col items-center justify-center h-full min-h-[60vh] gap-4">
      <div
        className="flex items-center justify-center rounded-2xl"
        style={{ width: 64, height: 64, background: `${color}26` }}
      >
        <UsersIcon className="w-8 h-8" style={{ color }} />
      </div>
      <div className="text-center">
        <h2 className="text-white font-semibold text-lg mb-1">People</h2>
        <p className="text-sm text-[#6B7280]">
          Contacts directory with linked messages and events.
          <br />
          Coming in issue <a href="https://github.com/tinkermonkey/context-library/issues/447" className="hover:underline" style={{ color }}>
            #447
          </a>.
        </p>
      </div>
    </div>
  );
}
