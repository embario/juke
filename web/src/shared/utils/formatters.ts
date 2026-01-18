export const formatDuration = (ms: number) => {
  if (!Number.isFinite(ms) || ms <= 0) {
    return '0:00';
  }
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, '0')}`;
};

export const formatReleaseDate = (date: string) => {
  if (!date) {
    return '—';
  }
  return new Date(date).getFullYear();
};
