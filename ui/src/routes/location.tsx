import { MapPinIcon } from '@heroicons/react/24/outline';
import { getDomainColor } from '../lib/designTokens';

const color = getDomainColor('location');

export default function LocationPage() {
  return (
    <div className="flex flex-col items-center justify-center h-full min-h-[60vh] gap-4">
      <div
        className="flex items-center justify-center rounded-2xl"
        style={{ width: 64, height: 64, background: `${color}26` }}
      >
        <MapPinIcon className="w-8 h-8" style={{ color }} />
      </div>
      <div className="text-center">
        <h2 className="text-white font-semibold text-lg mb-1">Location</h2>
        <p className="text-sm text-[#6B7280]">
          Place visit timeline and map overview.
          <br />
          Coming in issue <a href="https://github.com/tinkermonkey/context-library/issues/448" className="hover:underline" style={{ color }}>
            #448
          </a>.
        </p>
      </div>
    </div>
  );
}
