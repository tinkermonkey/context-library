// =============================================================================
// Heimdall design system — primitives, ported verbatim from
// @tinkermonkey/heimdall-ui (src/components/*.tsx) to in-browser JSX.
// Logic + class names are unchanged; only TypeScript types and ES imports
// were stripped, and components are attached to window for cross-file use.
// =============================================================================
const { forwardRef, useState, useRef, useCallback, useEffect } = React;

// ---- Icon.tsx -------------------------------------------------------------
const ICONS = {
  dashboard: 'M3 3 L10 3 L10 10 L3 10 Z M14 3 L21 3 L21 10 L14 10 Z M14 14 L21 14 L21 21 L14 21 Z M3 14 L10 14 L10 21 L3 21 Z',
  schema: 'M3 12 L9 6 L21 6 M3 12 L9 18 L21 18 M3 12 C4.7 12 6 10.3 6 8 C6 5.7 4.7 4 3 4 C1.3 4 0 5.7 0 8 C0 10.3 1.3 12 3 12 M21 6 C22.7 6 24 4.3 24 2 C24 0.3 22.7 0 21 0 C19.3 0 18 0.3 18 2 C18 4.3 19.3 6 21 6 M21 18 C22.7 18 24 16.3 24 14 C24 12.3 22.7 11 21 11 C19.3 11 18 12.3 18 14 C18 16.3 19.3 18 21 18',
  data: 'M12 5 C18.6 5 24 6.3 24 8 L24 8 L24 16 C24 17.7 18.6 19 12 19 C5.4 19 0 17.7 0 16 L0 8 C0 6.3 5.4 5 12 5 M3 5 L3 14 L21 14 L21 5 M3 11 L3 19 L21 19 L21 11',
  pipeline: 'M2 12 L6 12 L6 6 L18 6 L18 12 L22 12 M8 12 L16 12 M12 9 L15 12 L12 15',
  graph: 'M6 10 C8.8 10 11 7.8 11 5 C11 2.2 8.8 0 6 0 C3.2 0 1 2.2 1 5 C1 7.8 3.2 10 6 10 M18 10 C20.8 10 23 7.8 23 5 C23 2.2 20.8 0 18 0 C15.2 0 13 2.2 13 5 C13 7.8 15.2 10 18 10 M12 18 C14.8 18 17 15.8 17 13 C17 10.2 14.8 8 12 8 C9.2 8 7 10.2 7 13 C7 15.8 9.2 18 12 18 M8 8 L16 16 M16 8 L8 16 M12 9 L12 15',
  search: 'M10.6 14.8 C14.2 14.8 17.2 11.5 17.2 7.4 C17.2 3 14.2 0 10.6 0 C6.9 0 3 3 3 7.4 C3 11.5 6.9 14.8 10.6 14.8 M19.8 19.2 L16.7 16.3',
  bell: 'M6.55 9.7 C6.55 3.7 11.15 0 11.15 0 C11.15 0 15.75 3.7 15.75 9.7 C15.75 12 17.25 13.4 17.25 13.4 L4.6 13.4 C4.6 13.4 6.55 12 6.55 9.7 M9.4 19.4 C9.73 19.8 10.8 20.1 10.95 20.1 C11.1 20.1 12.18 19.8 12.5 19.4',
  plus: 'M12 5 L12 19 M5 12 L19 12',
  check: 'M2 12 L8 18 L22 4',
  x: 'M3 3 L21 21 M21 3 L3 21',
  chevronDown: 'M6 9 L12 15 L18 9',
  chevronUp: 'M18 15 L12 9 L6 15',
  chevronLeft: 'M15 6 L9 12 L15 18',
  chevronRight: 'M9 6 L15 12 L9 18',
  menu: 'M3 6 L21 6 M3 12 L21 12 M3 18 L21 18',
  settings: 'M12 1.5 C12.4 1.5 12.7 1.8 12.7 2.2 L12.7 4 C14.2 4.4 15.6 5.3 16.7 6.6 L18 5.4 C18.4 5.1 19 5.1 19.3 5.4 C19.7 5.7 19.7 6.3 19.3 6.6 L18 7.8 C19.2 8.9 20.2 10.3 20.6 12 L22.4 12 C22.9 12 23.2 12.3 23.2 12.8 C23.2 13.3 22.9 13.6 22.4 13.6 L20.6 13.6 C20.2 15.3 19.2 16.7 18 17.8 L19.3 19 C19.7 19.3 19.7 19.9 19.3 20.2 C19 20.5 18.4 20.5 18 20.2 L16.7 19 C15.6 20.3 14.2 21.2 12.7 21.6 L12.7 23.4 C12.7 23.8 12.4 24.1 12 24.1 C11.6 24.1 11.3 23.8 11.3 23.4 L11.3 21.6 C9.8 21.2 8.4 20.3 7.3 19 L6 20.2 C5.6 20.5 5 20.5 4.7 20.2 C4.3 19.9 4.3 19.3 4.7 19 L6 17.8 C4.8 16.7 3.8 15.3 3.4 13.6 L1.6 13.6 C1.1 13.6 0.8 13.3 0.8 12.8 C0.8 12.3 1.1 12 1.6 12 L3.4 12 C3.8 10.3 4.8 8.9 6 7.8 L4.7 6.6 C4.3 6.3 4.3 5.7 4.7 5.4 C5 5.1 5.6 5.1 6 5.4 L7.3 6.6 C8.4 5.3 9.8 4.4 11.3 4 L11.3 2.2 C11.3 1.8 11.6 1.5 12 1.5 Z M12 8.5 C10.6 8.5 9.5 9.6 9.5 11 C9.5 12.4 10.6 13.5 12 13.5 C13.4 13.5 14.5 12.4 14.5 11 C14.5 9.6 13.4 8.5 12 8.5 Z',
  alert: 'M12 2 L2 20 L22 20 Z M12 9 L12 13 M12 17 L12.01 17',
  trash: 'M3 6 L3 20 C3 21.1 3.9 22 5 22 L19 22 C20.1 22 21 21.1 21 20 L21 6 M1 6 L23 6 M7 6 L7 4 C7 2.9 7.9 2 9 2 L15 2 C16.1 2 17 2.9 17 4 L17 6 M9 11 L9 17 M15 11 L15 17',
  edit: 'M3 17.25 L3 21 L6.75 21 L17.81 9.94 L14.06 6.19 Z M20.71 7.04 C21.1 6.65 21.1 6.02 20.71 5.63 L18.37 3.29 C17.98 2.9 17.35 2.9 16.96 3.29 L15.12 5.12 L18.87 8.87 Z',
  download: 'M12 2 L12 13 M5 10 L12 17 L19 10',
  upload: 'M12 22 L12 11 M5 14 L12 7 L19 14',
  eye: 'M12 5 C7 5 2.73 8.11 1 12.46 C2.73 16.89 7 20 12 20 C17 20 21.27 16.89 23 12.46 C21.27 8.11 17 5 12 5 Z M12 16 C14.2 16 16 14.2 16 12 C16 9.8 14.2 8 12 8 C9.8 8 8 9.8 8 12 C8 14.2 9.8 16 12 16 Z',
  eyeOff: 'M12 5.69 C8.5 5.69 5.2 7.6 3.2 10.4 M21 19 L2 2 M9.88 9.88 C9.4 10.5 9 11.2 9 12 C9 14.21 10.79 16 13 16 C13.8 16 14.5 15.6 15.12 15.12 M18.8 10.4 C20.8 7.6 17.5 5.69 12 5.69',
  clock: 'M12 2 C6.48 2 2 6.48 2 12 C2 17.52 6.48 22 12 22 C17.52 22 22 17.52 22 12 C22 6.48 17.52 2 12 2 Z M12 20 C7.58 20 4 16.42 4 12 C4 7.58 7.58 4 12 4 C16.42 4 20 7.58 20 12 C20 16.42 16.42 20 12 20 Z M13 7 L11 7 L11 13 L16.25 15.85 L17 14.32 L13 12 Z',
  calendar: 'M5 2 L5 4 L19 4 L19 2 M3 4 L3 20 C3 21.1 3.9 22 5 22 L19 22 C20.1 22 21 21.1 21 20 L21 4 M7 11 L7 13 L9 13 L9 11 L7 11 Z M12 11 L12 13 L14 13 L14 11 L12 11 Z M17 11 L17 13 L19 13 L19 11 L17 11 Z',
  filter: 'M3 6 L21 6 L18 13 L18 20 L6 20 L6 13 Z',
  link: 'M10 11 C10.8 10.3 12 10.2 12.7 10.2 L20 10.2 C21 10.2 21.8 11 21.8 12 L21.8 19 C21.8 20 21 20.8 20 20.8 L12.7 20.8 C11.7 20.8 10.9 20 10.9 19 L10.9 12 C10.9 11.9 10.91 11.8 10.92 11.7 M7 11 C7.8 10.3 6.5 10.2 5.8 10.2 L1 10.2 C0.1 10.2 0.2 11 0.2 12 L0.2 19 C0.2 20 0.9 20.8 1.8 20.8 L5.8 20.8 C6.8 20.8 7.6 20 7.6 19 L7.6 12 C7.6 11.9 7.59 11.8 7.58 11.7',
  lock: 'M7 10 L7 7 C7 4.24 9.24 2 12 2 C14.76 2 17 4.24 17 7 L17 10 M5 10 L19 10 L19 20 C19 21.1 18.1 22 17 22 L7 22 C5.9 22 5 21.1 5 20 Z',
  unlock: 'M7 10 L19 10 L19 20 C19 21.1 18.1 22 17 22 L7 22 C5.9 22 5 21.1 5 20 L5 10 L5 7 C5 4.24 7.24 2 10 2 C12.76 2 15 4.24 15 7 L13 7 C13 5.34 11.66 4 10 4 C8.34 4 7 5.34 7 7 Z',
  user: 'M12 12 C13.66 12 15 10.66 15 9 C15 7.34 13.66 6 12 6 C10.34 6 9 7.34 9 9 C9 10.66 10.34 12 12 12 Z M12 22 C16.42 22 21 20 21 16 L21 14 C21 11.79 19.21 10 17 10 L7 10 C4.79 10 3 11.79 3 14 L3 16 C3 20 7.58 22 12 22 Z',
  copy: 'M16 1 L4 1 C2.9 1 2 1.9 2 3 L2 17 L4 17 L4 3 L16 3 Z M20 5 L8 5 C6.9 5 6 5.9 6 7 L6 21 C6 22.1 6.9 23 8 23 L20 23 C21.1 23 22 22.1 22 21 L22 7 C22 5.9 21.1 5 20 5 Z',
  info: 'M12 2 C6.48 2 2 6.48 2 12 C2 17.52 6.48 22 12 22 C17.52 22 22 17.52 22 12 C22 6.48 17.52 2 12 2 Z M13 17 L11 17 L11 11 L13 11 Z M13 9 L11 9 L11 7 L13 7 Z',
  help: 'M12 2 C6.48 2 2 6.48 2 12 C2 17.52 6.48 22 12 22 C17.52 22 22 17.52 22 12 C22 6.48 17.52 2 12 2 Z M13 19 L11 19 L11 17 L13 17 Z M15.07 10.25 C14.29 11.29 13.5 12 13 12.9 L13 14 L11 14 L11 13 C11 11.52 11.79 10.29 12.93 9.07 C13.62 8.29 14.29 7.5 14.29 6.5 C14.29 5.42 13.47 4.6 12.4 4.6 C11.4 4.6 10.6 5.36 10.6 6.3 L8.6 6.2 C8.72 4.5 10.09 3.1 12.4 3.1 C14.84 3.1 16.3 4.5 16.3 6.42 C16.3 7.8 15.66 8.9 15.07 10.25 Z',
  spinner: 'M12 2 C6.48 2 2 6.48 2 12 C2 17.52 6.48 22 12 22 C17.52 22 22 17.52 22 12 M12 2 C6.48 2 2 6.48 2 12',
  loading: 'M12 2 C6.48 2 2 6.48 2 12',
  moreVertical: 'M12 8 C13.1 8 14 7.1 14 6 C14 4.9 13.1 4 12 4 C10.9 4 10 4.9 10 6 C10 7.1 10.9 8 12 8 Z M12 14 C13.1 14 14 13.1 14 12 C14 10.9 13.1 10 12 10 C10.9 10 10 10.9 10 12 C10 13.1 10.9 14 12 14 Z M12 20 C13.1 20 14 19.1 14 18 C14 16.9 13.1 16 12 16 C10.9 16 10 16.9 10 18 C10 19.1 10.9 20 12 20 Z',
  moreHorizontal: 'M6 10 C4.9 10 4 10.9 4 12 C4 13.1 4.9 14 6 14 C7.1 14 8 13.1 8 12 C8 10.9 7.1 10 6 10 Z M18 10 C16.9 10 16 10.9 16 12 C16 13.1 16.9 14 18 14 C19.1 14 20 13.1 20 12 C20 10.9 19.1 10 18 10 Z M12 10 C10.9 10 10 10.9 10 12 C10 13.1 10.9 14 12 14 C13.1 14 14 13.1 14 12 C14 10.9 13.1 10 12 10 Z',
  reload: 'M7 7 C4.24 7 2 9.24 2 12 C2 14.56 3.68 16.73 6 17.73 L6 15.95 C4.29 15.16 3 13.32 3 11.13 C3 8.82 4.82 7 7 7 Z M17 7 C19.76 7 22 9.24 22 12 C22 14.13 20.71 15.97 18.7 16.76 L18.7 18.54 C21.32 17.54 23 15.56 23 13 C23 10.24 20.76 8 18 8 Z M11.5 5 L14.5 8 L8.5 8 Z M8.5 16 L14.5 16 L11.5 19 Z',
  arrowRight: 'M5 12 L19 12 M13 6 L19 12 L13 18',
  arrowLeft: 'M19 12 L5 12 M11 6 L5 12 L11 18',
  arrowUp: 'M12 19 L12 5 M6 11 L12 5 L18 11',
  arrowDown: 'M12 5 L12 19 M6 13 L12 19 L18 13',
  star: 'M12 2 L15.09 10.26 L24 10.26 L17.55 15.13 L19.64 23.39 L12 18.53 L4.36 23.39 L6.45 15.13 L0 10.26 L8.91 10.26 Z',
  heart: 'M20.84 4.61 C20.02 3.78 18.98 3.37 17.93 3.37 C16.88 3.37 15.84 3.78 15.02 4.61 L12 7.63 L8.98 4.61 C7.30 2.92 4.71 2.92 3.02 4.61 C1.33 6.30 1.33 8.88 3.02 10.57 L12 19.58 L20.99 10.57 C22.68 8.88 22.68 6.30 20.84 4.61 Z',
  palette: 'M12 2 C6.48 2 2 6.48 2 12 C2 17.52 6.48 22 12 22 C17.52 22 22 17.52 22 12 C22 6.48 17.52 2 12 2 Z M7 12 C8.1 12 9 11.1 9 10 C9 8.9 8.1 8 7 8 C5.9 8 5 8.9 5 10 C5 11.1 5.9 12 7 12 Z M17 12 C18.1 12 19 11.1 19 10 C19 8.9 18.1 8 17 8 C15.9 8 15 8.9 15 10 C15 11.1 15.9 12 17 12 Z M12 17 C10.9 17 10 16.1 10 15 C10 13.9 10.9 13 12 13 C13.1 13 14 13.9 14 15 C14 16.1 13.1 17 12 17 Z M7 17 C5.9 17 5 16.1 5 15 C5 13.9 5.9 13 7 13 C8.1 13 9 13.9 9 15 C9 16.1 8.1 17 7 17 Z M17 17 C15.9 17 15 16.1 15 15 C15 13.9 15.9 13 17 13 C18.1 13 19 13.9 19 15 C19 16.1 18.1 17 17 17 Z',
  component: 'M5 3 L19 3 L19 9 L5 9 Z M5 11 L19 11 L19 17 L5 17 Z M3 20 L21 20',
  table: 'M3 4 L21 4 M3 4 L3 20 L21 20 L21 4 M3 8 L21 8 M3 12 L21 12 M3 16 L21 16 M8 4 L8 20 M13 4 L13 20 M18 4 L18 20',
  layout: 'M3 3 L21 3 L21 21 L3 21 Z M3 8 L21 8 M3 3 L3 21 M8 8 L8 21',
  moon: 'M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z',
  sun: 'M12 3v2M12 19v2M5.64 5.64l1.42 1.42M16.95 16.95l1.41 1.41M3 12h2M19 12h2M5.64 18.36l1.41-1.41M16.95 7.05l1.41-1.41M12 7a5 5 0 1 0 0 10A5 5 0 0 0 12 7z',
  'bar-chart': 'M3 3 L3 20 L21 20 M5 16 L5 9 M12 16 L12 5 M19 16 L19 8',
  'trending-up': 'M23 6 L13.5 15.5 M23 6 L23 13 L16 13 M1 23 L6.5 17.5 L13 24 L23 6',
  'trending-down': 'M23 18 L13.5 8.5 M23 18 L23 11 L16 11 M1 1 L6.5 6.5 L13 0 L23 18',
  send: 'M16 8 L2 5 L9.5 12 L2 19 L16 16 M7 12 L16 12',
  bot: 'M12 2 C6.48 2 2 6.48 2 12 C2 17.52 6.48 22 12 22 C17.52 22 22 17.52 22 12 C22 6.48 17.52 2 12 2 Z M7 8 L7 10 L9 10 L9 8 Z M15 8 L15 10 L17 10 L17 8 Z M9 14 L15 14 M12 14 L12 18',
  paperclip: 'M12.5 2 C9.46 2 7 4.46 7 7.5 C7 10.54 9.46 13 12.5 13 L18 13 C18.55 13 19 12.55 19 12 C19 11.45 18.55 11 18 11 L12.5 11 C10.57 11 9 9.43 9 7.5 C9 5.57 10.57 4 12.5 4 C14.43 4 16 5.57 16 7.5 L16 15 C16 18.31 13.31 21 10 21 C6.69 21 4 18.31 4 15 L4 7 C4 5.9 4.9 5 6 5 C7.1 5 8 5.9 8 7 L8 15 C8 16.1 8.9 17 10 17 C11.1 17 12 16.1 12 15 L12 7.5',
  'pie-chart': 'M21.21 15.89 L12 12 L12 2.69 A10 10 0 0 1 21.21 15.89 M12 12 L5.5 5.5 A10 10 0 0 0 2 12 M2 12 A10 10 0 0 0 12 22 A10 10 0 0 0 12 12',
  slash: 'M21 3 L3 21',
  file: 'M14 2 L6 2 C4.9 2 4 2.9 4 4 L4 20 C4 21.1 4.9 22 6 22 L18 22 C19.1 22 20 21.1 20 20 L20 8 Z M14 2 L14 8 L20 8 M16 13 L8 13 M16 17 L8 17 M10 9 L8 9',
  zap: 'M13 2 L3 14 L12 14 L11 22 L21 10 L12 10 Z',
  hardDrive: 'M22 12 L2 12 M2 9 C2 7.9 2.9 7 4 7 L20 7 C21.1 7 22 7.9 22 9 L22 19 C22 20.1 21.1 21 20 21 L4 21 C2.9 21 2 20.1 2 19 Z M6 17 L6.01 17',
  folder: 'M20 20 C21.1 20 22 19.1 22 18 L22 8 C22 6.9 21.1 6 20 6 L12.1 6 C11.43 6 10.8 5.68 10.41 5.13 L9.6 3.9 C9.22 3.34 8.59 3 7.93 3 L4 3 C2.9 3 2 3.9 2 5 L2 18 C2 19.1 2.9 20 4 20 Z',
  tag: 'M12.59 2.59 C12.21 2.21 11.7 2 11.17 2 L4 2 C2.9 2 2 2.9 2 4 L2 11.17 C2 11.7 2.21 12.21 2.59 12.59 L11.29 21.29 C12.07 22.07 13.34 22.07 14.12 21.29 L20.7 14.71 C21.48 13.93 21.48 12.66 20.7 11.88 Z M7.5 7.5 L7.51 7.5',
  gitBranch: 'M6 3 L6 15 M6 6 C7.66 6 9 4.66 9 3 C9 1.34 7.66 0 6 0 C4.34 0 3 1.34 3 3 C3 4.66 4.34 6 6 6 Z M6 24 C7.66 24 9 22.66 9 21 C9 19.34 7.66 18 6 18 C4.34 18 3 19.34 3 21 C3 22.66 4.34 24 6 24 Z M18 9 C19.66 9 21 7.66 21 6 C21 4.34 19.66 3 18 3 C16.34 3 15 4.34 15 6 C15 7.66 16.34 9 18 9 Z M18 9 C18 13 15 15 9 15',
};

const Icon = forwardRef(({ name, size = 24, className = '', 'aria-label': ariaLabel, ...props }, ref) => {
  const pathData = ICONS[name];
  if (!pathData) { console.warn(`Icon "${name}" does not exist in ICONS map`); return null; }
  return (
    <svg ref={ref} viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor"
      strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"
      aria-hidden={ariaLabel ? undefined : true} aria-label={ariaLabel} className={className} style={props.style}>
      <path d={pathData} />
    </svg>
  );
});
Icon.displayName = 'Icon';

// ---- Button.tsx -----------------------------------------------------------
const Button = forwardRef(({ variant = 'primary', size = 'md', icon, className = '', disabled, type = 'button', ...props }, ref) => {
  const classNames = ['btn', `btn--${variant}`, `btn--${size}`, icon ? 'btn--icon' : '', className].filter(Boolean).join(' ');
  return <button ref={ref} type={type} disabled={disabled} className={classNames} style={props.style} onClick={props.onClick} aria-label={props['aria-label']}>{props.children}</button>;
});
Button.displayName = 'Button';

// ---- Chip.tsx -------------------------------------------------------------
const Chip = forwardRef(({ variant = 'neutral', form = 'default', className = '', children, ...props }, ref) => {
  const classNames = ['chip', `chip--${form}`, form === 'default' && `chip--${variant}`, className].filter(Boolean).join(' ');
  return (
    <span ref={ref} className={classNames} style={props.style} onClick={props.onClick}>
      {form === 'default' && <span className="chip__dot" />}
      {form === 'env' && <span className="chip__dot chip__dot--env" />}
      {children}
    </span>
  );
});
Chip.displayName = 'Chip';

// ---- Badge.tsx ------------------------------------------------------------
const Badge = forwardRef(({ color = 'cyan', pulse = false, className = '', ...props }, ref) => {
  const classNames = ['badge', `badge--${color}`, pulse && 'badge--pulse', className].filter(Boolean).join(' ');
  return <span ref={ref} className={classNames} style={props.style} />;
});
Badge.displayName = 'Badge';

const StatusBadge = forwardRef(({ color = 'cyan', pulse = false, className = '', role = 'img', ...props }, ref) => {
  const classNames = ['status-badge', `status-badge--${color}`, pulse && 'status-badge--pulse', className].filter(Boolean).join(' ');
  return <div ref={ref} role={role} className={classNames} style={props.style} />;
});
StatusBadge.displayName = 'StatusBadge';

// ---- VersionPill.tsx ------------------------------------------------------
const VersionPill = forwardRef(({ className = '', children, ...props }, ref) => {
  const classNames = ['version-pill', className].filter(Boolean).join(' ');
  return <span ref={ref} className={classNames} style={props.style}>{children}</span>;
});
VersionPill.displayName = 'VersionPill';

// ---- SegmentedControl.tsx -------------------------------------------------
const SegmentedControl = forwardRef(({ value, onChange, options, disabled = false, className = '', ...props }, ref) => {
  const classNames = ['segmented-control', disabled ? 'segmented-control--disabled' : '', className].filter(Boolean).join(' ');
  const buttonRefs = useRef([]);
  const handleKeyDown = useCallback((e, index) => {
    const enabledIndices = options.map((o, i) => (o.disabled ? null : i)).filter((i) => i !== null);
    const currentPos = enabledIndices.indexOf(index);
    let nextPos;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { e.preventDefault(); nextPos = enabledIndices[(currentPos + 1) % enabledIndices.length]; }
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { e.preventDefault(); nextPos = enabledIndices[(currentPos - 1 + enabledIndices.length) % enabledIndices.length]; }
    if (nextPos !== undefined) { buttonRefs.current[nextPos]?.focus(); onChange(options[nextPos].value); }
  }, [options, onChange]);
  const hasMatch = options.some((o) => o.value === value);
  const firstEnabledIndex = options.findIndex((o) => !o.disabled);
  return (
    <div ref={ref} className={classNames} role="radiogroup" style={props.style}>
      {options.map((option, index) => {
        const isActive = value === option.value;
        const tabIndex = isActive ? 0 : (!hasMatch && index === firstEnabledIndex ? 0 : -1);
        return (
          <button key={option.value} ref={(el) => { buttonRefs.current[index] = el; }}
            className={`segmented-control__segment ${isActive ? 'segmented-control__segment--active' : ''}`}
            onClick={() => !disabled && !option.disabled && onChange(option.value)}
            onKeyDown={(e) => handleKeyDown(e, index)} type="button" role="radio"
            aria-checked={isActive} disabled={disabled || option.disabled} tabIndex={tabIndex}>
            {option.label}
          </button>
        );
      })}
    </div>
  );
});
SegmentedControl.displayName = 'SegmentedControl';

Object.assign(window, { ICONS, Icon, Button, Chip, Badge, StatusBadge, VersionPill, SegmentedControl });
