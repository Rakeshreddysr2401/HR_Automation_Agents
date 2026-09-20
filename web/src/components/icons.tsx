/**
 * Inline icon set. Hand-drawn against a 24-box on a 1.8 stroke, rather than a
 * dependency: the app uses about twenty glyphs, and an icon font or package
 * would be a larger download than the entire JS bundle.
 *
 * Every icon inherits `currentColor` and sizes off `em`, so an icon beside text
 * tracks that text's size and colour automatically — which is what keeps the
 * density switch from needing per-icon rules.
 */
import type { SVGProps } from "react";

type Props = SVGProps<SVGSVGElement> & { size?: number | string };

function Svg({ size = "1em", children, ...rest }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      focusable="false"
      {...rest}
    >
      {children}
    </svg>
  );
}

export const IconPlay = (p: Props) => <Svg {...p}><polygon points="6 4 20 12 6 20 6 4" /></Svg>;

export const IconSun = (p: Props) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="4.2" />
    <path d="M12 2v2M12 20v2M4.2 4.2l1.5 1.5M18.3 18.3l1.5 1.5M2 12h2M20 12h2M4.2 19.8l1.5-1.5M18.3 5.7l1.5-1.5" />
  </Svg>
);

export const IconMoon = (p: Props) => (
  <Svg {...p}><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></Svg>
);

export const IconMonitor = (p: Props) => (
  <Svg {...p}>
    <rect x="2.5" y="3.5" width="19" height="13" rx="2" />
    <path d="M8.5 20.5h7M12 16.5v4" />
  </Svg>
);

export const IconRows = (p: Props) => (
  <Svg {...p}>
    <rect x="3" y="4" width="18" height="5.5" rx="1.5" />
    <rect x="3" y="14.5" width="18" height="5.5" rx="1.5" />
  </Svg>
);

export const IconCompact = (p: Props) => (
  <Svg {...p}><path d="M3 6h18M3 10.5h18M3 15h18M3 19.5h18" /></Svg>
);

export const IconPalette = (p: Props) => (
  <Svg {...p}>
    <path d="M12 21a9 9 0 1 1 9-9c0 2.3-1.9 3-3.4 3H16a2 2 0 0 0-1.4 3.4A2 2 0 0 1 12 21z" />
    <circle cx="8" cy="10" r="1.1" fill="currentColor" stroke="none" />
    <circle cx="12" cy="7.5" r="1.1" fill="currentColor" stroke="none" />
    <circle cx="16" cy="10" r="1.1" fill="currentColor" stroke="none" />
  </Svg>
);

export const IconUpload = (p: Props) => (
  <Svg {...p}>
    <path d="M21 15v3.5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V15" />
    <path d="M7.5 8.5 12 4l4.5 4.5M12 4v11.5" />
  </Svg>
);

export const IconFile = (p: Props) => (
  <Svg {...p}>
    <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
    <path d="M14 3v5h5" />
  </Svg>
);

export const IconCheck = (p: Props) => <Svg {...p}><path d="M4.5 12.5l5 5 10-11" /></Svg>;

export const IconAlert = (p: Props) => (
  <Svg {...p}>
    <path d="M10.3 3.9 2.6 17.2A2 2 0 0 0 4.3 20.2h15.4a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
    <path d="M12 9v4M12 16.5h.01" />
  </Svg>
);

export const IconFlag = (p: Props) => (
  <Svg {...p}><path d="M4.5 21V4M4.5 5h11l-1.4 3.6 1.4 3.6h-11" /></Svg>
);

export const IconQuestion = (p: Props) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9.2" />
    <path d="M9.6 9.3a2.5 2.5 0 1 1 3.4 2.3c-.6.3-1 .9-1 1.6v.4M12 17h.01" />
  </Svg>
);

export const IconArrow = (p: Props) => <Svg {...p}><path d="M4 12h15M13.5 6.5 20 12l-6.5 5.5" /></Svg>;

export const IconSearch = (p: Props) => (
  <Svg {...p}><circle cx="11" cy="11" r="7" /><path d="M16.2 16.2 21 21" /></Svg>
);

export const IconRefresh = (p: Props) => (
  <Svg {...p}>
    <path d="M20.5 12a8.5 8.5 0 1 1-2.6-6.1" />
    <path d="M20.5 4.5V10H15" />
  </Svg>
);

export const IconUndo = (p: Props) => (
  <Svg {...p}>
    <path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1" />
    <path d="M3.5 4.5V10H9" />
  </Svg>
);

export const IconDownload = (p: Props) => (
  <Svg {...p}>
    <path d="M21 15v3.5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V15" />
    <path d="M7.5 11 12 15.5 16.5 11M12 4v11.5" />
  </Svg>
);

export const IconShield = (p: Props) => (
  <Svg {...p}>
    <path d="M12 21s7.5-3.4 7.5-9.2V5.6L12 3 4.5 5.6v6.2C4.5 17.6 12 21 12 21z" />
    <path d="M9 12l2.2 2.2L15.5 10" />
  </Svg>
);

export const IconMap = (p: Props) => (
  <Svg {...p}>
    <path d="M4 5.5v14l5-2 6 2 5-2V3.5l-5 2-6-2-5 2z" />
    <path d="M9 3.5v14M15 5.5v14" />
  </Svg>
);

export const IconList = (p: Props) => (
  <Svg {...p}>
    <path d="M8.5 6h12M8.5 12h12M8.5 18h12" />
    <circle cx="4.2" cy="6" r="1.1" fill="currentColor" stroke="none" />
    <circle cx="4.2" cy="12" r="1.1" fill="currentColor" stroke="none" />
    <circle cx="4.2" cy="18" r="1.1" fill="currentColor" stroke="none" />
  </Svg>
);

export const IconTable = (p: Props) => (
  <Svg {...p}>
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <path d="M3 9.5h18M3 15h18M9.5 9.5V20" />
  </Svg>
);

export const IconClock = (p: Props) => (
  <Svg {...p}><circle cx="12" cy="12" r="9.2" /><path d="M12 7.2V12l3.4 2" /></Svg>
);

export const IconBrain = (p: Props) => (
  <Svg {...p}>
    <path d="M12 5.2a3 3 0 0 0-5.6-1.1A2.9 2.9 0 0 0 4 8.8a3 3 0 0 0 .5 5A3 3 0 0 0 9 18.9a3 3 0 0 0 3-.6z" />
    <path d="M12 5.2a3 3 0 0 1 5.6-1.1A2.9 2.9 0 0 1 20 8.8a3 3 0 0 1-.5 5A3 3 0 0 1 15 18.9a3 3 0 0 1-3-.6z" />
    <path d="M12 5.2v13.1" />
  </Svg>
);

export const IconSpark = (p: Props) => (
  <Svg {...p}>
    <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />
    <path d="M18.5 16.5l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z" />
  </Svg>
);

export const IconX = (p: Props) => <Svg {...p}><path d="M6 6l12 12M18 6 6 18" /></Svg>;

export const IconChevron = (p: Props) => <Svg {...p}><path d="M9 6l6 6-6 6" /></Svg>;

export const IconTrash = (p: Props) => (
  <Svg {...p}>
    <path d="M4 7h16M9.5 7V4.8h5V7M6 7l1 13h10l1-13" />
  </Svg>
);
