export const colors = {
  background: '#FAFAFA',
  surface: '#FFFFFF',
  ink: '#262626',
  muted: '#737373',
  line: '#DBDBDB',
  brand: '#0095F6',
  brandDark: '#1877F2',
  teal: '#00BA88',
  sunny: '#F59E0B',
  danger: '#ED4956',
  ok: '#00BA88',
  card: '#FAFAFA',
  violet: '#8134AF',
  blue: '#0095F6',
} as const;

export const radius = {
  sm: 8,
  md: 8,
  lg: 8,
  pill: 999,
} as const;

/** Instagram story ring gradient stops (unviewed). */
export const storyGradient = ['#FEDA75', '#FA7E1E', '#D62976', '#962FBF', '#4F5BD5'] as const;

/** Viewed-story ring color. */
export const storySeen = '#D9D9D9';

/** Shared shadow/elevation presets — use instead of ad-hoc shadows. */
export const shadow = {
  card: {
    shadowColor: '#000000',
    shadowOpacity: 0.08,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 2,
  },
  pop: {
    shadowColor: '#000000',
    shadowOpacity: 0.16,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 6 },
    elevation: 6,
  },
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
} as const;

export const type = {
  hero: 24,
  title: 20,
  subtitle: 16,
  body: 14,
  caption: 12,
} as const;
