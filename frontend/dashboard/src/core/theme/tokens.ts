// CSS source of truth is globals.css @theme; this file exists for TS-side consumers
// (charts, canvas, inline styles) and must stay in sync with Color.kt (light scheme)
// and Shapes.kt via the CSS tokens in globals.css.

/** M3 light palette — mirrors Color.kt OpenWellnessLightColors. */
export const colors = {
  primary: '#006a60',
  onPrimary: '#ffffff',
  primaryContainer: '#74f8e5',
  onPrimaryContainer: '#00201c',
  secondary: '#4a635f',
  onSecondary: '#ffffff',
  secondaryContainer: '#cce8e2',
  onSecondaryContainer: '#051f1c',
  error: '#ba1a1a',
  onError: '#ffffff',
  errorContainer: '#ffdad6',
  onErrorContainer: '#410002',
  background: '#fafdfb',
  onBackground: '#191c1b',
  surface: '#fafdfb',
  onSurface: '#191c1b',
  surfaceVariant: '#dae5e1',
  onSurfaceVariant: '#3f4947',
  outline: '#6f7976',
  outlineVariant: '#bec9c5',
} as const

/** Shape radii in px — mirrors Shapes.kt OpenWellnessShapes. */
export const radii = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 28,
} as const

export type ColorToken = keyof typeof colors
export type RadiusToken = keyof typeof radii
