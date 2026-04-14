import { MusicalNoteIcon } from '@heroicons/react/24/outline';
import { getDomainColor } from '../lib/designTokens';

const color = getDomainColor('music');

export default function MusicPage() {
  return (
    <div className="flex flex-col items-center justify-center h-full min-h-[60vh] gap-4">
      <div
        className="flex items-center justify-center rounded-2xl"
        style={{ width: 64, height: 64, background: `${color}26` }}
      >
        <MusicalNoteIcon className="w-8 h-8" style={{ color }} />
      </div>
      <div className="text-center">
        <h2 className="text-white font-semibold text-lg mb-1">Music</h2>
        <p className="text-sm text-[#6B7280]">
          Apple Music library catalog and listening history.
          <br />
          Coming in issue <a href="https://github.com/tinkermonkey/context-library/issues/449" className="hover:underline" style={{ color }}>
            #449
          </a>.
        </p>
      </div>
    </div>
  );
}
