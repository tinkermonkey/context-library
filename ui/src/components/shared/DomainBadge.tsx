import type { ReactNode } from 'react';
import { Chip } from '@tinkermonkey/heimdall-ui';
import { DOMAIN_NAMES } from '../../lib/designTokens';

interface DomainBadgeProps {
  domain: string;
}

export function DomainBadge({ domain }: DomainBadgeProps): ReactNode {
  const isKnownDomain = (DOMAIN_NAMES as readonly string[]).includes(domain);

  const style = isKnownDomain
    ? ({
        color: `rgb(var(--domain-${domain}))`,
        backgroundColor: `rgb(var(--domain-${domain}) / 0.12)`,
        borderColor: `rgb(var(--domain-${domain}) / 0.25)`,
      } as React.CSSProperties)
    : undefined;

  return (
    <Chip form="id-tag" style={style}>
      {domain}
    </Chip>
  );
}
