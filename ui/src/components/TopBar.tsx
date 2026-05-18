import { Topbar, type TopbarProps } from '@tinkermonkey/heimdall-ui';

interface TopBarComponentProps extends Omit<TopbarProps, 'breadcrumbs'> {
  title?: string;
  subtitle?: string;
  breadcrumbs?: Array<{
    label: string;
    href?: string;
    onClick?: () => void;
  }>;
}

export function TopBar({
  title,
  subtitle,
  breadcrumbs,
  children,
  ...topbarProps
}: TopBarComponentProps) {
  const breadcrumbsToShow = breadcrumbs || (title ? [{ label: title }] : []);

  return (
    <>
      <Topbar
        breadcrumbs={breadcrumbsToShow}
        {...topbarProps}
      >
        {children}
      </Topbar>
      {subtitle && (
        <div
          className="px-6 py-3 text-sm"
          style={{ color: 'rgb(var(--shell-fg-2))' }}
        >
          {subtitle}
        </div>
      )}
    </>
  );
}
