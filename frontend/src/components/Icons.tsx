import type { SVGProps } from 'react'

type Props = SVGProps<SVGSVGElement> & { size?: number }

function Base({ size = 16, children, ...rest }: Props) {
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
      {...rest}
    >
      {children}
    </svg>
  )
}

export const IconBox = (p: Props) => (
  <Base {...p}>
    <path d="M21 8.5 12 3 3 8.5v7L12 21l9-5.5v-7Z" />
    <path d="M3 8.5 12 14l9-5.5M12 14v7" />
  </Base>
)

export const IconList = (p: Props) => (
  <Base {...p}>
    <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />
  </Base>
)

export const IconSettings = (p: Props) => (
  <Base {...p}>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0v-.1A1.6 1.6 0 0 0 6.9 19.6l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 3 14.4H3a2 2 0 1 1 0-4h.1A1.6 1.6 0 0 0 4.4 7.6l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.6 1.6 0 0 0 10 4.6V4a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 2.6 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8v.4a1.6 1.6 0 0 0 1.4 1.3H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.4 1.3Z" />
  </Base>
)

export const IconSearch = (p: Props) => (
  <Base {...p}>
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-3.5-3.5" />
  </Base>
)

export const IconPlus = (p: Props) => (
  <Base {...p}>
    <path d="M12 5v14M5 12h14" />
  </Base>
)

export const IconX = (p: Props) => (
  <Base {...p}>
    <path d="M18 6 6 18M6 6l12 12" />
  </Base>
)

export const IconExternal = (p: Props) => (
  <Base {...p}>
    <path d="M14 4h6v6M20 4l-8 8M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4" />
  </Base>
)

export const IconCalendar = (p: Props) => (
  <Base {...p}>
    <rect x="3" y="5" width="18" height="16" rx="2" />
    <path d="M8 3v4M16 3v4M3 11h18" />
  </Base>
)

export const IconUpload = (p: Props) => (
  <Base {...p}>
    <path d="M12 16V4M7 9l5-5 5 5M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
  </Base>
)

export const IconChevronDown = (p: Props) => (
  <Base {...p}>
    <path d="m6 9 6 6 6-6" />
  </Base>
)

export const IconDots = (p: Props) => (
  <Base {...p}>
    <circle cx="5" cy="12" r="1.4" />
    <circle cx="12" cy="12" r="1.4" />
    <circle cx="19" cy="12" r="1.4" />
  </Base>
)

export const IconSpark = (p: Props) => (
  <Base {...p}>
    <path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18" />
  </Base>
)

export const IconHelp = (p: Props) => (
  <Base {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M9.5 9a2.5 2.5 0 1 1 3.4 2.3c-.6.3-.9.8-.9 1.4v.3M12 17h.01" />
  </Base>
)

export const IconRefresh = (p: Props) => (
  <Base {...p}>
    <path d="M21 12a9 9 0 1 1-3-6.7M21 4v5h-5" />
  </Base>
)

export const IconTrash = (p: Props) => (
  <Base {...p}>
    <path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
  </Base>
)

export const IconCheckCircle = (p: Props) => (
  <Base {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="m8.5 12.5 2.5 2.5 4.5-5" />
  </Base>
)

export const IconXCircle = (p: Props) => (
  <Base {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M15 9l-6 6M9 9l6 6" />
  </Base>
)

export const IconAlert = (p: Props) => (
  <Base {...p}>
    <path d="M10.3 4.6 2.9 17a1.8 1.8 0 0 0 1.5 2.7h15.2A1.8 1.8 0 0 0 21.1 17L13.7 4.6a1.8 1.8 0 0 0-3.4 0Z" />
    <path d="M12 9v4M12 16.5h.01" />
  </Base>
)

export const IconSpinner = (p: Props) => (
  <Base {...p} className={`animate-spin ${p.className ?? ''}`}>
    <path d="M12 3a9 9 0 1 0 9 9" />
  </Base>
)

export const IconHeart = (p: Props) => (
  <Base {...p}>
    <path d="M12 20s-7-4.4-7-9.3A4.2 4.2 0 0 1 12 7.7a4.2 4.2 0 0 1 7 3c0 4.9-7 9.3-7 9.3Z" />
  </Base>
)

export const IconStar = (p: Props) => (
  <Base {...p}>
    <path d="m12 4 2.4 4.9 5.4.8-3.9 3.8.9 5.4-4.8-2.6-4.8 2.6.9-5.4L4.2 9.7l5.4-.8Z" />
  </Base>
)

export const IconCart = (p: Props) => (
  <Base {...p}>
    <circle cx="9" cy="19" r="1.6" />
    <circle cx="17" cy="19" r="1.6" />
    <path d="M3 4h2.2l2.1 10.2A2 2 0 0 0 9.3 16h8.2a2 2 0 0 0 2-1.6L21 7H6" />
  </Base>
)

export const IconCopy = (p: Props) => (
  <Base {...p}>
    <rect x="9" y="9" width="11" height="11" rx="2" />
    <path d="M15 5.5A1.5 1.5 0 0 0 13.5 4h-8A1.5 1.5 0 0 0 4 5.5v8A1.5 1.5 0 0 0 5.5 15" />
  </Base>
)
