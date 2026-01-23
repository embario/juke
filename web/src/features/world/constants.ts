export const GENRE_COLORS: Record<string, string> = {
  pop: '#FF6B9D',
  rock: '#E74C3C',
  country: '#F39C12',
  rap: '#9B59B6',
  'hip-hop': '#9B59B6',
  folk: '#27AE60',
  jazz: '#3498DB',
  classical: '#1ABC9C',
};

export const DEFAULT_GENRE_COLOR = '#95A5A6';

export const SUPER_GENRES = Object.keys(GENRE_COLORS);

export function getGenreColor(genre: string): string {
  const normalized = genre.toLowerCase().trim();
  return GENRE_COLORS[normalized] ?? DEFAULT_GENRE_COLOR;
}

export const LOD_CLOUT_THRESHOLDS: Record<number, number> = {
  1: 0.5,
  2: 0.5,
  3: 0.5,
  4: 0.5,
  5: 0.2,
  6: 0.2,
  7: 0.2,
  8: 0.2,
  9: 0.05,
  10: 0.05,
  11: 0.05,
  12: 0.05,
};
